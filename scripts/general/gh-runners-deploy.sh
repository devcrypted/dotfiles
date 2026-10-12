#!/usr/bin/env bash
# tms-runners.sh v2.4 — turn any Ubuntu VM into N self-healing, dockerized GitHub Actions
# self-hosted runners (org- or repo-level). Works on any cloud or bare metal.
#
# ── QUICK START ──────────────────────────────────────────────────────────────────────────
#   read -rs GH_TOKEN && export GH_TOKEN          # paste token; not stored in shell history
#   ./tms-runners.sh --org project-tms --labels tms-local,docker -n 2
#   (no sudo needed — the script elevates itself and keeps your env vars)
#
# ── COMMANDS ─────────────────────────────────────────────────────────────────────────────
#   (none) | up        install everything, log in, converge to N runners   [default]
#   status             containers + runner state/labels as GitHub sees them
#   logs [N]           follow logs of runner N (default 1)
#   heal               restart unhealthy/stopped runner containers now
#   down [--purge]     deregister + delete ALL runners (do this before deleting the VM)
#
# ── COMMON TASKS ─────────────────────────────────────────────────────────────────────────
#   scale to 6 runners        ./tms-runners.sh -n 6
#   change labels             ./tms-runners.sh --labels tms-local,docker
#   cap resources per runner  ./tms-runners.sh --memory 1500m --cpus 1
#   force OS upgrade          ./tms-runners.sh --upgrade        (only the 1st run upgrades by default)
#   rebuild image + recreate  ./tms-runners.sh --rebuild        (interrupts running jobs)
#   repo-level runners        ./tms-runners.sh --repo OWNER/REPO
#   Settings are saved in /etc/tms-runners.conf, so later runs only need the flags you change.
#
# ── ENV VARS / AUTH ──────────────────────────────────────────────────────────────────────
#   GH_TOKEN or GITHUB_TOKEN   token for GitHub API calls. If unset, the script prints a
#                              device-login link + code for you to approve in a browser.
#   --token-file PATH          read the token from a file instead (use with plain `sudo`,
#                              which strips env vars; or use `sudo -E`).
#   Token permissions (note: "Actions: Read and write" alone is NOT enough):
#     fine-grained, org runners : Resource owner = the org, Organization permission
#                                 "Self-hosted runners" = Read and write
#     fine-grained, repo runners: Repository permission "Administration" = Read and write
#     classic                   : scope admin:org (org) or repo (repo)
#   The token is used only for API calls on this VM — never written to disk, never passed
#   to containers (they get a one-hour registration token). Pass it again on later runs.
#
# ── WHAT A RERUN DOES (idempotent — every step checks real state) ────────────────────────
#   • Changed --labels / --memory / --cpus / --host-docker / new image: idle runners are
#     stopped, deregistered from GitHub, deleted (container + volumes) and recreated with the
#     new settings. A runner that is running a job is skipped and rolled on the next run.
#   • Lower -n: extra runners are removed + deregistered (busy ones wait for the next run).
#   • Runner deleted in the GitHub UI: re-registered. Container stopped/unhealthy: restarted
#     (also every 5 min by a systemd timer).
#   • Safe after any failure, Ctrl-C or SSH drop — just rerun the same command.
#
# ── LABELS ───────────────────────────────────────────────────────────────────────────────
#   GitHub adds self-hosted, Linux and X64/ARM64 itself. --labels adds yours (default
#   tms-local,docker). A job runs only if ALL labels in its `runs-on:` exist on the runner,
#   e.g. `runs-on: tms-local` or `runs-on: [self-hosted, linux, tms-local]`.
#
# Log: /var/log/tms-runners/tms-runners.log
set -Eeuo pipefail
trap '' HUP

APP=tms-runners
CONF=/etc/${APP}.conf
BASE=/opt/${APP}
STATE=/var/lib/${APP}
LOGDIR=/var/log/${APP}
LOG=${LOGDIR}/${APP}.log
LOCK=/var/lock/${APP}.lock
IMAGE=tms-gh-runner:local
HOST_SHORT=$(hostname -s)
PREFIX="ghr-${HOST_SHORT}"
TOTAL=14
STEP_N=0
STEP_T0=$SECONDS
T0=$SECONDS

# ---- defaults (overridden by saved config, then by flags) -------------------
CMD=up
COUNT=""
TARGET_KIND=""
TARGET=""
LABELS_EXTRA="tms-local,docker"
DOCKER_MODE="dind"
NODE_MAJOR=22
MEM_LIMIT=""
CPU_LIMIT=""
REBUILD=0
KEEP_LOGIN=0
PURGE=0
FORCE_UPGRADE=0
SKIP_UPGRADE=0
AUTO_REBOOT=0
LOGN=1
LOGGED_IN_BY_US=0
EXIT_CODE=0
RUN_OUT=""
RUNNER_URL=""
GH_LIST=""
GH_OK=0

usage() {
  cat <<'EOF'
Usage: sudo ./tms-runners.sh [up|status|logs [N]|heal|down] [options]

  -n, --count N         number of runners (default 4; rerun with a new N to scale)
      --org ORG         org-level runners (recommended: serve every repo in the org)
      --repo OWNER/REPO repo-level runners
      --labels a,b      extra runner labels (default: tms-local,docker)
      --host-docker     share the host Docker daemon instead of per-runner Docker-in-Docker
      --node-major N    Node.js major baked into the runner image (default 22)
      --memory 1500m    per-runner memory limit        --cpus 1.5   per-runner CPU limit
      --upgrade         force apt update+full-upgrade (default: only on the first run)
      --skip-upgrade    never run apt full-upgrade
      --rebuild         rebuild image from scratch and recreate every runner (interrupts jobs)
      --auto-reboot     reboot at the end if the OS upgrade requires it (runners come back alone)
      --keep-login      keep gh logged in afterwards (default: log out if this run logged in)
      --purge           with 'down': also delete the runner image

GitHub auth (no browser needed): export a token and pass --org/--repo.
      export GH_TOKEN=github_pat_...   (or GITHUB_TOKEN)   then:  ./tms-runners.sh --org my-org
      --token-file PATH   read the token from a file (use this if you run via plain 'sudo', which drops env vars)
  Fine-grained PAT, org runners : Resource owner = the org, Organization permission 'Self-hosted runners' = Read and write
  Fine-grained PAT, repo runners: Repository permission 'Administration' = Read and write
  Classic PAT                   : scope admin:org (org) or repo (repo)
  NOTE: 'Actions: Read and write' alone does NOT let a token register runners.
  The token is used only on this VM for API calls; it is never written to disk or passed to containers.
Log: /var/log/tms-runners/tms-runners.log
EOF
}

# ---- run as root ------------------------------------------------------------
[[ $EUID -eq 0 ]] || exec sudo -E bash "$0" "$@"
export HOME=/root DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a NEEDRESTART_SUSPEND=1
mkdir -p "$LOGDIR" "$STATE" "$BASE"
if [[ -z ${GH_TOKEN:-} && -n ${GITHUB_TOKEN:-} ]]; then export GH_TOKEN=$GITHUB_TOKEN; fi
rm -f "$STATE"/run.* 2>/dev/null || true

# ---- UI helpers -------------------------------------------------------------
if [[ -t 1 ]]; then
  B=$'\033[1m'; D=$'\033[2m'; R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; N=$'\033[0m'
else
  B=''; D=''; R=''; G=''; Y=''; N=''
fi
say()  { printf '%s\n' "$*" 2>/dev/null || true; }
fmt_t() { printf '%02d:%02d' $(($1 / 60)) $(($1 % 60)); }
logf() { printf '[%s] %s\n' "$(date -Is)" "$*" >>"$LOG" 2>/dev/null || true; }
step() {
  STEP_N=$((STEP_N + 1)); STEP_T0=$SECONDS
  say ""; say "${B}[${STEP_N}/${TOTAL}] $1${N}"; logf "STEP ${STEP_N}/${TOTAL}: $1"
}
ok()   { say "   ${G}✔${N} $* ${D}($(fmt_t $((SECONDS - STEP_T0))))${N}"; logf "ok: $*"; }
skip() { say "   ${D}• $* — nothing to do${N}"; logf "skip: $*"; }
info() { say "   $*"; logf "info: $*"; }
warn() { say "   ${Y}! $*${N}"; logf "WARN: $*"; }
die() {
  say ""; say "${R}✘ ERROR:${N} $*"
  say "${D}  Log: ${LOG}${N}"
  say "${D}  Fix the cause (or just wait a minute) and rerun the same command — it resumes where it stopped.${N}"
  logf "ERROR: $*"; exit 1
}
trap 'die "unexpected failure at line $LINENO: $BASH_COMMAND"' ERR

_run_once() {
  local start=$SECONDS pid rc=0 i=0 line cols spin_last=$SECONDS frames='|/-\'
  RUN_OUT=$(mktemp "$STATE/run.XXXXXX")
  logf "\$ $*"
  "$@" >"$RUN_OUT" 2>&1 </dev/null &
  pid=$!
  cols=$(tput cols 2>/dev/null || echo 100)
  while kill -0 "$pid" 2>/dev/null; do
    line=$(tail -c 600 "$RUN_OUT" 2>/dev/null | tr '\r' '\n' | tr -d '\000-\010\013-\037' | grep -v '^[[:space:]]*$' | tail -n1 | cut -c1-$((cols - 18)) || true)
    if [[ -t 1 ]]; then
      printf '\r\033[K   %s %s  %s%s%s' "${frames:i%4:1}" "$(fmt_t $((SECONDS - start)))" "$D" "$line" "$N" 2>/dev/null || true
    elif (( SECONDS - spin_last >= 30 )); then
      say "   … $(fmt_t $((SECONDS - start))) $line"; spin_last=$SECONDS
    fi
    i=$((i + 1)); sleep 0.25
  done
  wait "$pid" || rc=$?
  if [[ -t 1 ]]; then printf '\r\033[K' 2>/dev/null || true; fi
  cat "$RUN_OUT" >>"$LOG" 2>/dev/null || true
  return "$rc"
}
# run <cmd…>: live progress, output → log; retries via RETRIES=n; dies on final failure.
run() {
  local tries=${RETRIES:-1} attempt=1 rc=0
  while :; do
    if _run_once "$@"; then rm -f "$RUN_OUT"; return 0; else rc=$?; fi
    if (( attempt >= tries )); then
      say "   ${R}✘ failed (exit $rc): $*${N}"
      say "   ${D}--- last output ---${N}"
      { tail -n 25 "$RUN_OUT" 2>/dev/null | sed 's/^/   | /'; } || true
      die "command failed: $*"
    fi
    attempt=$((attempt + 1))
    warn "retry ${attempt}/${tries} in $((attempt * 5))s"
    sleep $((attempt * 5))
  done
}
run_soft() { _run_once "$@" && rm -f "$RUN_OUT"; }

write_file() { # write_file <path> <mode> < content   → 0 if changed, 1 if identical
  local path=$1 mode=${2:-644} tmp
  tmp=$(mktemp)
  cat >"$tmp"
  if [[ -f $path ]] && cmp -s "$tmp" "$path"; then rm -f "$tmp"; return 1; fi
  install -m "$mode" "$tmp" "$path"; rm -f "$tmp"; return 0
}

# ---- apt helpers ------------------------------------------------------------
wait_apt() {
  local end=$((SECONDS + 1200)) warned=0
  local locks=(/var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock /var/cache/apt/archives/lock)
  while (( SECONDS < end )); do
    if command -v fuser >/dev/null; then
      fuser "${locks[@]}" >/dev/null 2>&1 || return 0
    else
      pgrep -x 'apt|apt-get|dpkg|unattended-upgr' >/dev/null || return 0
    fi
    if (( warned == 0 )); then echo "waiting for another apt/dpkg process (boot-time updates) to finish…"; warned=1; fi
    sleep 5
  done
  echo "apt/dpkg lock still held after 20 min — inspect: ps aux | grep -E 'apt|dpkg|unattended'"
  return 1
}
apt_get() {
  wait_apt || return 1
  apt-get -o Acquire::Retries=5 -o DPkg::Lock::Timeout=300 \
    -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold "$@"
}
apt_i() { apt_get install -y --no-install-recommends "$@"; }
pkg_installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q 'install ok installed'; }
mem_mb() { awk '/MemTotal/{print int($2/1024)}' /proc/meminfo; }
free_gb() { df -BG --output=avail / | tail -1 | tr -dc 0-9; }

# ---- github helpers ---------------------------------------------------------
api_path() { if [[ $TARGET_KIND == org ]]; then echo "orgs/$TARGET"; else echo "repos/$TARGET"; fi; }
reg_token() { gh api -X POST "$(api_path)/actions/runners/registration-token" --jq .token; }
load_gh_runners() {
  GH_OK=0; GH_LIST=""
  if GH_LIST=$(gh api "$(api_path)/actions/runners" --paginate \
      --jq '.runners[] | [.name, .status, (.busy|tostring), ([.labels[].name]|join(","))] | @tsv' 2>/dev/null); then GH_OK=1; fi
}
gh_field() { awk -F'\t' -v n="$1" -v f="$2" '$1==n{print $f}' <<<"$GH_LIST"; }
gh_delete_runner() {
  local id
  id=$(gh api "$(api_path)/actions/runners" --paginate --jq ".runners[] | select(.name==\"$1\") | .id" 2>/dev/null | head -n1 || true)
  if [[ -n $id ]]; then gh api -X DELETE "$(api_path)/actions/runners/$id" >/dev/null 2>&1 || true; fi
}
has_env_token() { [[ -n ${GH_TOKEN:-}${GITHUB_TOKEN:-} ]]; }
token_kind() {
  case ${GH_TOKEN:-${GITHUB_TOKEN:-}} in
    github_pat_*) echo fine-grained ;;
    ghp_*)        echo classic ;;
    ghs_*)        echo app ;;
    gho_*|ghu_*)  echo oauth ;;
    '')           echo none ;;
    *)            echo unknown ;;
  esac
}
PROBE_ERR=""
probe_access() { # can this token mint a runner registration token for the target?
  local out
  if out=$(gh api -X POST "$(api_path)/actions/runners/registration-token" --jq .token 2>&1); then PROBE_ERR=""; return 0; fi
  PROBE_ERR=$out; return 1
}
access_hint() {
  say "   GitHub answered: ${PROBE_ERR:-(no message)}"
  case "$(token_kind):${TARGET_KIND}" in
    fine-grained:org)  say "   → Fine-grained PAT: Resource owner must be '${TARGET}' (org must allow fine-grained PATs and approve the token); Organization permission 'Self-hosted runners' = Read and write." ;;
    fine-grained:repo) say "   → Fine-grained PAT: Repository access must include ${TARGET}; Repository permission 'Administration' = Read and write." ;;
    classic:org)       say "   → Classic PAT: scope admin:org (plus repo if the org has private repos). If the org uses SAML SSO, authorize the token for it." ;;
    classic:repo)      say "   → Classic PAT: scope repo, and the token's user must be admin of ${TARGET}. Authorize for SSO if required." ;;
    app:*)             say "   → GitHub App installation token: needs 'Self-hosted runners' (org) or 'Administration' (repo) = write." ;;
    *)                 say "   → The token's user must be an admin of the ${TARGET_KIND}; org runners need admin:org / 'Self-hosted runners' write." ;;
  esac
  say "   → 'Actions: Read and write' alone is NOT enough to register runners."
}
validate_env_token() {
  local kind login scopes
  kind=$(token_kind)
  info "token from environment (${kind})"
  if [[ $kind != app ]]; then
    if ! login=$(gh api user --jq .login 2>&1); then
      die "GitHub rejected the token (${login}). Expired, revoked, or mistyped? If you ran 'sudo ./tms-runners.sh', sudo dropped your env var — use 'sudo -E', run without sudo, or --token-file."
    fi
    info "authenticated as ${login}"
  fi
  if [[ $kind == classic ]]; then
    scopes=$(gh api -i user 2>/dev/null | tr -d '\r' | awk -F': ' 'tolower($1)=="x-oauth-scopes"{print $2}' || true)
    info "classic token scopes: ${scopes:-none}"
    if [[ -n $TARGET_KIND ]]; then
      case $TARGET_KIND in
        org)  [[ $scopes == *admin:org* ]] || warn "scope admin:org missing — org runner calls will fail" ;;
        repo) [[ $scopes == *repo* ]]      || warn "scope repo missing — repo runner calls will fail" ;;
      esac
    fi
  fi
}
gh_login_cmd() { # $1 = login|refresh ; non-interactive device flow prints URL + code, no Enter needed
  gh auth "$1" --hostname github.com --scopes repo,admin:org "${@:2}"
}
do_auth() {
  if has_env_token; then validate_env_token; ok "token accepted"; return 0; fi
  if gh auth status --hostname github.com >/dev/null 2>&1; then
    ok "already logged in as $(gh api user --jq .login 2>/dev/null || echo '?')"; return 0
  fi
  say ""
  say "   ${B}ACTION NEEDED (one time):${N} a link and a one-time code are printed below."
  say "   Open the link on any device, enter the code, approve. The script continues by itself."
  say ""
  if ! gh_login_cmd login --git-protocol https --web </dev/null; then
    [[ -t 0 ]] || die "gh login failed and there is no TTY. Export GH_TOKEN (see --help) and rerun."
    warn "retrying interactively"
    gh_login_cmd login --git-protocol https --web
  fi
  LOGGED_IN_BY_US=1
  ok "logged in as $(gh api user --jq .login 2>/dev/null || echo '?')"
}

# ---- docker helpers ---------------------------------------------------------
existing_indexes() {
  command -v docker >/dev/null || return 0
  { docker ps -a --filter "name=^${PREFIX}-[0-9]+\$" --format '{{.Names}}' | sed "s/^${PREFIX}-//" | sort -n; } || true
}
cfg_hash() { printf '%s' "$RUNNER_URL|$LABELS_EXTRA|$DOCKER_MODE|$MEM_LIMIT|$CPU_LIMIT|$(docker image inspect -f '{{.Id}}' "$IMAGE" 2>/dev/null)" | sha256sum | cut -c1-12; }
container_age() { # seconds since (re)start, 0 if unknown
  local s
  s=$(docker inspect -f '{{.State.StartedAt}}' "$1" 2>/dev/null) || { echo 0; return; }
  s=$(date -d "$s" +%s 2>/dev/null) || { echo 0; return; }
  echo $(( $(date +%s) - s ))
}
remove_one() { # remove_one <index> [keep-github]
  local i=$1 c="${PREFIX}-$1"
  docker stop -t 20 "$c" >/dev/null 2>&1 || true
  docker rm -f "$c" >/dev/null 2>&1 || true
  docker volume rm -f "$c-home" "$c-docker" >/dev/null 2>&1 || true
  if [[ ${2:-} != keep-github ]]; then gh_delete_runner "${HOST_SHORT}-$i"; fi
}
create_one() {
  local i=$1 c="${PREFIX}-$1" tok cfg
  docker volume rm -f "$c-home" "$c-docker" >/dev/null 2>&1 || true
  tok=$(RETRIES=3 retry_cmd reg_token)
  cfg=$(cfg_hash)
  local args=(run -d --name "$c" --init --restart unless-stopped
    --label "tms.app=$APP" --label "tms.cfg=$cfg"
    --health-cmd 'pgrep -f Runner.Listener >/dev/null || exit 1'
    --health-interval 30s --health-timeout 10s --health-retries 3 --health-start-period 180s
    -e RUNNER_URL="$RUNNER_URL" -e RUNNER_TOKEN="$tok" -e RUNNER_NAME="${HOST_SHORT}-$i"
    -e RUNNER_LABELS="$LABELS_EXTRA" -e DOCKER_MODE="$DOCKER_MODE"
    -v "$c-home:/home/runner/actions-runner")
  if [[ $DOCKER_MODE == host ]]; then
    args+=(-v /var/run/docker.sock:/var/run/docker.sock)
  else
    args+=(--privileged -v "$c-docker:/var/lib/docker")
  fi
  if [[ -n $MEM_LIMIT ]]; then args+=(--memory "$MEM_LIMIT"); fi
  if [[ -n $CPU_LIMIT ]]; then args+=(--cpus "$CPU_LIMIT"); fi
  args+=("$IMAGE")
  docker "${args[@]}" >/dev/null
}
retry_cmd() { # retry_cmd <cmd…> with RETRIES=n ; prints stdout of the successful attempt
  local tries=${RETRIES:-3} a=1 out
  while :; do
    if out=$("$@" 2>/dev/null); then printf '%s' "$out"; return 0; fi
    (( a >= tries )) && return 1
    a=$((a + 1)); sleep $((a * 3))
  done
}

# ---- disk helpers -----------------------------------------------------------
disk_help() {
  say "   Root disk is $(df -h --output=size / | tail -1 | tr -d ' ') with $(free_gb) GB free. Grow it, then rerun this script:"
  say "   • AWS: EC2 console → Volumes → this instance's root volume → Modify volume → set size (free tier covers up to 30 GB EBS — verify on your Free Tier page) → wait ~1 min."
  say "     The script grows the partition + filesystem itself on the next run."
  say "   • Other clouds/VMs: enlarge the disk in the provider console, then rerun."
}
grow_root() { # grow root partition + fs into space added to the cloud volume; no-op when already full
  local part disk pnum fstype dsz psz
  part=$(lsblk -rno NAME,MOUNTPOINT | awk '$2=="/"{print $1; exit}')
  [[ -n $part && -e /sys/class/block/$part/partition ]] || return 0
  disk="/dev/$(lsblk -no PKNAME "/dev/$part" | head -n1)"
  pnum=$(cat "/sys/class/block/$part/partition")
  dsz=$(blockdev --getsize64 "$disk"); psz=$(blockdev --getsize64 "/dev/$part")
  (( dsz - psz > 1073741824 )) || return 0
  info "disk is $((dsz >> 30)) GiB but the root partition only $((psz >> 30)) GiB → growing it"
  if ! pkg_installed cloud-guest-utils; then RETRIES=3 run apt_get update; run apt_i cloud-guest-utils; fi
  run_soft growpart "$disk" "$pnum" || true   # exit 1 just means NOCHANGE
  fstype=$(findmnt -no FSTYPE /)
  case $fstype in
    ext2|ext3|ext4) run resize2fs "/dev/$part" ;;
    xfs)            run xfs_growfs / ;;
    *)              warn "unknown root filesystem '$fstype' — grow it manually"; return 0 ;;
  esac
  ok "root filesystem is now $(df -h --output=size / | tail -1 | tr -d ' ')"
}
ensure_disk() { # ensure_disk <min_free_gb> — reclaim caches first, then fail with instructions
  local need=$1
  if (( $(free_gb) >= need )); then return 0; fi
  warn "only $(free_gb) GB free, need ${need} GB — reclaiming caches"
  run_soft apt-get clean || true
  run_soft journalctl --vacuum-size=50M || true
  if command -v docker >/dev/null; then
    run_soft docker builder prune -af || true
    run_soft docker image prune -f || true
  fi
  if (( $(free_gb) >= need )); then info "reclaimed → $(free_gb) GB free"; return 0; fi
  disk_help
  die "not enough disk space: $(free_gb) GB free, need ${need} GB"
}

# ---- config -----------------------------------------------------------------
save_conf() {
  {
    printf 'TARGET_KIND=%q\nTARGET=%q\nCOUNT=%q\nLABELS_EXTRA=%q\n' "$TARGET_KIND" "$TARGET" "${COUNT:-4}" "$LABELS_EXTRA"
    printf 'DOCKER_MODE=%q\nNODE_MAJOR=%q\nMEM_LIMIT=%q\nCPU_LIMIT=%q\n' "$DOCKER_MODE" "$NODE_MAJOR" "$MEM_LIMIT" "$CPU_LIMIT"
  } | write_file "$CONF" 600 || true
}
if [[ -f $CONF ]]; then
  # shellcheck disable=SC1090
  source "$CONF"
fi
while [[ $# -gt 0 ]]; do
  case $1 in
    up|status|down|logs|heal) CMD=$1 ;;
    [0-9]*)              LOGN=$1 ;;
    -n|--count)          COUNT=${2:?missing value}; shift ;;
    --org)               TARGET_KIND=org;  TARGET=${2:?missing value}; shift ;;
    --repo)              TARGET_KIND=repo; TARGET=${2:?missing value}; shift ;;
    --labels)            LABELS_EXTRA=${2:?missing value}; shift ;;
    --host-docker)       DOCKER_MODE=host ;;
    --node-major)        NODE_MAJOR=${2:?missing value}; shift ;;
    --memory)            MEM_LIMIT=${2:?missing value}; shift ;;
    --cpus)              CPU_LIMIT=${2:?missing value}; shift ;;
    --upgrade)           FORCE_UPGRADE=1 ;;
    --skip-upgrade)      SKIP_UPGRADE=1 ;;
    --rebuild)           REBUILD=1 ;;
    --auto-reboot)       AUTO_REBOOT=1 ;;
    --token-file)        [[ -r ${2:-} ]] || die "--token-file: cannot read '${2:-}'"
                         GH_TOKEN=$(tr -d '[:space:]' <"$2"); export GH_TOKEN; shift ;;
    --keep-login)        KEEP_LOGIN=1 ;;
    --purge)             PURGE=1 ;;
    -h|--help)           usage; exit 0 ;;
    *)                   usage; die "unknown argument: $1" ;;
  esac
  shift
done

cleanup() {
  if (( LOGGED_IN_BY_US == 1 && KEEP_LOGIN == 0 )); then
    gh auth logout --hostname github.com </dev/null >/dev/null 2>&1 || true
    say ""; say "   ${D}gh logged out — admin token removed from this VM (--keep-login to keep it).${N}"
  fi
}
trap cleanup EXIT
trap 'say ""; say "Interrupted. A running step may finish in the background; wait a minute, then rerun to resume."; exit 130' INT TERM

# ---- END HELPERS ------------------------------------------------------------

choose_target() {
  if [[ -z $TARGET ]]; then
    [[ -t 0 ]] || die "no target saved. Pass --org ORG or --repo OWNER/REPO (required when using GH_TOKEN non-interactively)."
    local orgs=() choice
    mapfile -t orgs < <(gh api user/orgs --paginate --jq '.[].login' 2>/dev/null || true)
    if (( ${#orgs[@]} == 0 )); then
      local ans
      read -rp "   Org name (or owner/repo for one repo): " ans
      if [[ $ans == */* ]]; then TARGET_KIND=repo; else TARGET_KIND=org; fi
      TARGET=$ans
    else
    say "   Register runners for:"
    PS3="   Pick a number: "
    select choice in "${orgs[@]/#/org: }" "a single repo"; do
      case $choice in
        "org: "*)        TARGET_KIND=org;  TARGET=${choice#org: }; break ;;
        "a single repo") TARGET_KIND=repo; read -rp "   owner/repo: " TARGET; break ;;
      esac
    done
    fi
  fi
  if [[ $TARGET_KIND == org ]]; then
    [[ $TARGET =~ ^[A-Za-z0-9-]+$ ]] || die "bad org name: $TARGET"
  else
    [[ $TARGET =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || die "repo must be OWNER/REPO: $TARGET"
  fi
  RUNNER_URL="https://github.com/$TARGET"
}

net_check() { # net_check <url>  — any HTTP answer counts; 000 = unreachable
  local code a
  for a in 1 2 3; do
    code=$(curl -sS -o /dev/null -m 10 -w '%{http_code}' "$1" 2>/dev/null || true)
    [[ $code != 000 && -n $code ]] && return 0
    sleep $((a * 2))
  done
  return 1
}

write_image_files() {
  mkdir -p "$BASE/image"
  write_file "$BASE/image/Dockerfile" 644 <<'DOCKERFILE' || true
FROM ubuntu:24.04
ARG RUNNER_VERSION
ARG NODE_MAJOR=22
ARG IMG_HASH=dev
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 \
    AGENT_TOOLSDIRECTORY=/opt/hostedtoolcache RUNNER_TOOL_CACHE=/opt/hostedtoolcache

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg git git-lfs jq unzip zip xz-utils tar sudo tzdata wget procps \
      build-essential python3 python3-pip python3-venv openssh-client rsync iptables \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" > /etc/apt/sources.list.d/docker.list \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
 && curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
 && apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin gh nodejs \
 && rm -rf /var/lib/apt/lists/*

RUN corepack enable \
 && npm install -g wrangler && npm cache clean --force \
 && arch="$(dpkg --print-architecture)" \
 && curl -fsSL "https://github.com/supabase/cli/releases/latest/download/supabase_linux_${arch}.tar.gz" | tar -xz -C /usr/local/bin supabase \
 && supabase --version && wrangler --version

RUN useradd -m -s /bin/bash runner \
 && usermod -aG docker runner \
 && echo 'runner ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/runner \
 && mkdir -p /opt/hostedtoolcache && chown runner:runner /opt/hostedtoolcache

RUN set -eux; \
    case "$(dpkg --print-architecture)" in amd64) ra=x64;; arm64) ra=arm64;; esac; \
    mkdir -p /home/runner/actions-runner && cd /home/runner/actions-runner; \
    curl -fsSL -o r.tgz "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-${ra}-${RUNNER_VERSION}.tar.gz"; \
    tar xzf r.tgz && rm r.tgz; \
    ./bin/installdependencies.sh; \
    rm -rf /var/lib/apt/lists/*; \
    chown -R runner:runner /home/runner

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
LABEL tms.hash=$IMG_HASH
ENTRYPOINT ["/entrypoint.sh"]
DOCKERFILE

  write_file "$BASE/image/entrypoint.sh" 755 <<'ENTRYPOINT' || true
#!/usr/bin/env bash
set -Eeuo pipefail
RUNNER_DIR=/home/runner/actions-runner
cd "$RUNNER_DIR"
chown runner:runner "$RUNNER_DIR" || true

if [[ "${DOCKER_MODE:-dind}" == "host" ]]; then
  # align container 'docker' group with the host socket's group
  if [[ -S /var/run/docker.sock ]]; then
    groupmod -o -g "$(stat -c %g /var/run/docker.sock)" docker
  fi
else
  # stale pid files break dockerd after 'docker restart'
  rm -f /var/run/docker.pid /run/docker.pid /run/docker/containerd/containerd.pid /var/run/docker/containerd/containerd.pid
  # cgroup v2 nesting (same trick as the official docker:dind entrypoint)
  if [[ -f /sys/fs/cgroup/cgroup.controllers ]]; then
    mkdir -p /sys/fs/cgroup/init
    xargs -rn1 < /sys/fs/cgroup/cgroup.procs > /sys/fs/cgroup/init/cgroup.procs || true
    sed -e 's/ / +/g' -e 's/^/+/' < /sys/fs/cgroup/cgroup.controllers > /sys/fs/cgroup/cgroup.subtree_control || true
  fi
  dockerd > /var/log/dockerd.log 2>&1 &
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 1; done
  docker info >/dev/null 2>&1 || { echo "dockerd failed to start:"; tail -n 50 /var/log/dockerd.log; exit 1; }
  # housekeeping inside this runner's own daemon
  ( while sleep 86400; do
      docker image prune -af --filter "until=168h"
      docker builder prune -af --filter "until=168h"
    done ) >/dev/null 2>&1 &
fi

if [[ ! -f .runner ]]; then
  : "${RUNNER_URL:?}" "${RUNNER_TOKEN:?}" "${RUNNER_NAME:?}"
  runuser -u runner -- env HOME=/home/runner ./config.sh --unattended --replace \
    --url "$RUNNER_URL" --token "$RUNNER_TOKEN" --name "$RUNNER_NAME" \
    --labels "${RUNNER_LABELS:-}" --work _work
fi
unset RUNNER_TOKEN
exec runuser -u runner -- env HOME=/home/runner ./run.sh
ENTRYPOINT
}

# =============================== UP =========================================
cmd_up() {
  COUNT=${COUNT:-4}
  if ! [[ $COUNT =~ ^[0-9]+$ ]] || (( COUNT < 1 || COUNT > 50 )); then die "count must be 1-50"; fi
  say "${B}tms-runners${N} — target: ${COUNT} runner(s), docker mode: ${DOCKER_MODE}, host: ${HOST_SHORT}"
  say "${D}log: ${LOG}${N}"

  # 1 ---------------------------------------------------------------- preflight
  step "Preflight checks"
  local os_id arch
  os_id=$(. /etc/os-release; echo "${ID:-}")
  [[ $os_id == ubuntu ]] || die "Ubuntu only (found '${os_id:-unknown}')"
  arch=$(dpkg --print-architecture)
  case $arch in amd64|arm64) ;; *) die "unsupported CPU arch: $arch" ;; esac
  info "Ubuntu $(. /etc/os-release; echo "$VERSION_ID") / $arch / $(mem_mb) MB RAM / $(free_gb) GB free disk"
  for u in https://github.com https://api.github.com https://download.docker.com https://registry-1.docker.io/v2/ http://archive.ubuntu.com; do
    net_check "$u" || die "cannot reach $u over IPv4. Check VM outbound rules / security group / public IP."
  done
  grow_root
  ensure_disk 10
  local rec=$(( 8 + 3 * COUNT ))
  if [[ $DOCKER_MODE == host ]]; then rec=14; fi
  if (( $(free_gb) < rec )); then
    warn "$(free_gb) GB free; ~${rec} GB recommended for ${COUNT} runner(s). Each Docker-in-Docker runner keeps its own image cache — one 'supabase start' pulls several GB into it. Fewer runners (-n) or --host-docker (shared cache) use less."
  fi
  ok "network, OS and disk look good"

  # 2 ------------------------------------------------------ repair package state
  step "Package manager sanity"
  if [[ -n $(dpkg --audit 2>/dev/null || true) ]]; then
    info "interrupted dpkg state detected — repairing"
    run apt_get -y -f install
    run dpkg --configure -a
    ok "repaired"
  else
    skip "dpkg state clean"
  fi

  # 3 ----------------------------------------------------------- update + upgrade
  step "System update + upgrade"
  local idx=()
  mapfile -t idx < <(existing_indexes)
  if (( SKIP_UPGRADE == 1 )); then
    skip "--skip-upgrade given"
  elif (( FORCE_UPGRADE == 1 || ${#idx[@]} == 0 )); then
    RETRIES=3 run apt_get update
    run apt_get -y full-upgrade
    ok "system fully upgraded"
  else
    skip "runners already deployed (use --upgrade to force; upgrades can restart Docker)"
  fi

  # 4 --------------------------------------------------------------- base packages
  step "Base packages"
  local want=(ca-certificates curl gnupg git jq unzip zip tar psmisc procps util-linux) missing=() p
  for p in "${want[@]}"; do pkg_installed "$p" || missing+=("$p"); done
  if (( ${#missing[@]} )); then
    RETRIES=3 run apt_get update
    run apt_i "${missing[@]}"
    ok "installed: ${missing[*]}"
  else
    skip "all present"
  fi
  install -m 0755 -d /etc/apt/keyrings

  # 5 ------------------------------------------------------------- swap + sysctl
  step "Swap + kernel tuning"
  local mem swap changed=0
  mem=$(mem_mb); swap=$(awk '/SwapTotal/{print int($2/1024)}' /proc/meminfo)
  if (( mem < 4096 && swap < 1024 )); then
    if [[ ! -e /swapfile ]]; then
      if (( $(free_gb) > 12 )); then
        info "RAM ${mem} MB → creating 2 GB swap"
        run bash -c 'fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048'
        chmod 600 /swapfile; mkswap /swapfile >/dev/null; swapon /swapfile; changed=1
      else
        warn "low RAM and not enough disk for swap"
      fi
    elif ! swapon --show=NAME --noheadings | grep -q '^/swapfile'; then
      swapon /swapfile || warn "could not enable existing /swapfile"; changed=1
    fi
  fi
  if [[ -e /swapfile ]] && ! grep -q '^/swapfile' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' >> /etc/fstab; changed=1
  fi
  if write_file /etc/sysctl.d/99-tms-runners.conf 644 <<'EOF'
fs.inotify.max_user_watches=524288
fs.inotify.max_user_instances=1024
vm.swappiness=20
EOF
  then sysctl -q -p /etc/sysctl.d/99-tms-runners.conf >/dev/null 2>&1 || true; changed=1; fi
  if (( changed )); then ok "swap/sysctl configured"; else skip "swap + sysctl already set"; fi
  local per=$(( mem / COUNT ))
  if (( per < 1500 )); then
    warn "${mem} MB RAM / ${COUNT} runners = ${per} MB each. Idle is fine, but parallel Playwright / 'supabase start' jobs will crawl or OOM. Sensible here: $(( mem / 1500 > 0 ? mem / 1500 : 1 )) runner(s)."
  fi

  # 6 ------------------------------------------------------------------- docker
  step "Docker engine"
  if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
    skip "docker $(docker version -f '{{.Server.Version}}' 2>/dev/null) running"
  else
    local codename
    codename=$(. /etc/os-release; echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
    if curl -fsSI -m 15 "https://download.docker.com/linux/ubuntu/dists/${codename}/Release" >/dev/null 2>&1; then
      info "using Docker's official repo (${codename})"
      RETRIES=3 run curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
      chmod a+r /etc/apt/keyrings/docker.asc
      echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${codename} stable" \
        > /etc/apt/sources.list.d/docker.list
      RETRIES=3 run apt_get update
      run apt_i docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    else
      warn "download.docker.com has no '${codename}' repo yet → using Ubuntu's docker.io"
      RETRIES=3 run apt_get update
      run apt_i docker.io
      run_soft apt_i docker-buildx docker-compose-v2 || true
    fi
    ok "docker installed"
  fi
  if [[ ! -f /etc/docker/daemon.json ]]; then
    mkdir -p /etc/docker
    write_file /etc/docker/daemon.json 644 <<'EOF' || true
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }
EOF
    info "log rotation configured — restarting docker (no runners exist yet)"
    systemctl restart docker
  fi
  systemctl enable --now docker >/dev/null 2>&1 || true
  local a
  for a in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 2; done
  docker info >/dev/null 2>&1 || die "docker daemon is not responding"
  ok "docker $(docker version -f '{{.Server.Version}}') ready"

  # 7 ------------------------------------------------------------------ gh cli
  step "GitHub CLI"
  if command -v gh >/dev/null; then
    skip "gh $(gh --version | head -1 | awk '{print $3}') installed"
  else
    RETRIES=3 run curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg
    chmod a+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list
    RETRIES=3 run apt_get update
    run apt_i gh
    ok "gh installed"
  fi

  # 8 ------------------------------------------------------------------- auth
  step "GitHub authentication"
  do_auth

  # 9 ------------------------------------------------------- target + access
  step "Target + access check"
  choose_target
  save_conf
  info "target: ${TARGET_KIND} '${TARGET}'"
  local tr
  for tr in 1 2 3; do
    probe_access && break
    case $PROBE_ERR in *"HTTP 401"*|*"HTTP 403"*|*"HTTP 404"*) break ;; esac
    sleep $((tr * 3))
  done
  if [[ -n $PROBE_ERR ]] && ! has_env_token; then
    warn "token lacks permission — requesting extra scopes (approve the new code)"
    gh_login_cmd refresh </dev/null || true
    probe_access || true
  fi
  if [[ -n $PROBE_ERR ]]; then
    access_hint
    die "cannot create runner registration tokens for ${TARGET_KIND} '${TARGET}'"
  fi
  ok "admin access confirmed"

  # 10 ------------------------------------------------------------- image
  step "Runner image"
  write_image_files
  local img_hash cur_hash rv
  img_hash="$(cat "$BASE/image/Dockerfile" "$BASE/image/entrypoint.sh" | sha256sum | cut -c1-12)-n${NODE_MAJOR}"
  cur_hash=$(docker image inspect -f '{{index .Config.Labels "tms.hash"}}' "$IMAGE" 2>/dev/null || true)
  if (( REBUILD == 0 )) && [[ $cur_hash == "$img_hash" ]]; then
    skip "image $IMAGE is current ($img_hash)"
  else
    ensure_disk 8
    rv=$(RETRIES=3 retry_cmd gh api repos/actions/runner/releases/latest --jq .tag_name) || die "could not resolve latest actions/runner version"
    rv=${rv#v}
    info "building (runner v${rv}, node ${NODE_MAJOR}) — first build takes several minutes"
    local bargs=(build --pull --progress=plain -t "$IMAGE" --build-arg "RUNNER_VERSION=$rv"
                 --build-arg "NODE_MAJOR=$NODE_MAJOR" --build-arg "IMG_HASH=$img_hash")
    if (( REBUILD == 1 )); then bargs+=(--no-cache); fi
    RETRIES=2 run docker "${bargs[@]}" "$BASE/image"
    ok "image built"
  fi

  # 11 ---------------------------------------------------------- runners
  step "Runners (converge to ${COUNT})"
  load_gh_runners
  if (( GH_OK == 0 )); then warn "could not list runners on GitHub — skipping GitHub-side drift checks"; fi
  local cfg i c cur age state busy created=0 recreated=0 removed=0 kept=0
  cfg=$(cfg_hash)
  mapfile -t idx < <(existing_indexes)
  for i in $(seq 1 "$COUNT"); do
    c="${PREFIX}-$i"
    if ! docker inspect "$c" >/dev/null 2>&1; then
      create_one "$i"; created=$((created + 1)); info "runner ${i}/${COUNT}: created"
      continue
    fi
    cur=$(docker inspect -f '{{index .Config.Labels "tms.cfg"}}' "$c" 2>/dev/null || true)
    state=$(gh_field "${HOST_SHORT}-$i" 2)
    busy=$(gh_field "${HOST_SHORT}-$i" 3)
    age=$(container_age "$c")
    if (( REBUILD == 1 )); then
      remove_one "$i"; create_one "$i"; recreated=$((recreated + 1)); info "runner ${i}/${COUNT}: rebuilt"
    elif [[ $cur != "$cfg" ]]; then
      if [[ $busy == true ]]; then
        warn "runner ${i}: config/image changed but it is running a job — will roll on next run"; kept=$((kept + 1))
      else
        remove_one "$i"; create_one "$i"; recreated=$((recreated + 1)); info "runner ${i}/${COUNT}: recreated (config or image changed)"
      fi
    elif (( GH_OK == 1 )) && [[ -z $state ]] && (( age > 240 )); then
      remove_one "$i" keep-github; create_one "$i"; recreated=$((recreated + 1))
      info "runner ${i}/${COUNT}: was missing on GitHub → re-registered"
    else
      if [[ $(docker inspect -f '{{.State.Running}}' "$c") != true ]]; then
        docker start "$c" >/dev/null; info "runner ${i}/${COUNT}: was stopped → started"
      else
        info "runner ${i}/${COUNT}: ok"
      fi
      kept=$((kept + 1))
    fi
  done
  for i in "${idx[@]}"; do
    if (( i > COUNT )); then
      busy=$(gh_field "${HOST_SHORT}-$i" 3)
      if [[ $busy == true ]]; then warn "runner ${i}: extra but busy — remove on next run"
      else remove_one "$i"; removed=$((removed + 1)); info "runner ${i}: removed (above target count)"; fi
    fi
  done
  ok "created ${created}, recreated ${recreated}, kept ${kept}, removed ${removed}"

  # 12 --------------------------------------------------- self-heal + logrotate
  step "Self-healing + log rotation"
  local sd=0
  write_file /usr/local/sbin/tms-runners-heal 755 <<'EOF' && sd=1 || true
#!/bin/sh
command -v docker >/dev/null 2>&1 || exit 0
for c in $(docker ps -q --filter 'name=^ghr-' --filter 'health=unhealthy'); do docker restart "$c"; done
for c in $(docker ps -aq --filter 'name=^ghr-' --filter 'status=exited'); do docker start "$c"; done
EOF
  write_file /etc/systemd/system/tms-runners-heal.service 644 <<'EOF' && sd=1 || true
[Unit]
Description=Restart unhealthy/exited GitHub runner containers
After=docker.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/tms-runners-heal
EOF
  write_file /etc/systemd/system/tms-runners-heal.timer 644 <<'EOF' && sd=1 || true
[Unit]
Description=Periodic runner self-heal
[Timer]
OnBootSec=3min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
EOF
  write_file /etc/logrotate.d/tms-runners 644 <<'EOF' && sd=1 || true
/var/log/tms-runners/*.log {
  weekly
  rotate 4
  compress
  missingok
  notifempty
}
EOF
  if [[ $DOCKER_MODE == host ]]; then
    write_file "/etc/cron.daily/${APP}-prune" 755 <<'EOF' && sd=1 || true
#!/bin/sh
docker image prune -af --filter "until=168h" >/dev/null 2>&1
docker builder prune -af --filter "until=168h" >/dev/null 2>&1
EOF
  fi
  if (( sd )); then systemctl daemon-reload; fi
  systemctl enable --now tms-runners-heal.timer >/dev/null 2>&1 || warn "could not enable heal timer"
  if (( sd )); then ok "heal timer (every 5 min) + logrotate installed"; else skip "already installed"; fi

  # 13 ------------------------------------------------------------- wait
  step "Waiting for runners to come online"
  local w0=$SECONDS end=$((SECONDS + 300)) got=0 last=-1
  while :; do
    load_gh_runners
    got=$(awk -F'\t' -v p="${HOST_SHORT}-" -v c="$COUNT" \
      'index($1,p)==1 && $2=="online"{n=substr($1,length(p)+1); if (n ~ /^[0-9]+$/ && n+0>=1 && n+0<=c) k++} END{print k+0}' <<<"$GH_LIST")
    if [[ -t 1 ]]; then
      printf '\r\033[K   online on GitHub: %s/%s  %s(%s)%s' "$got" "$COUNT" "$D" "$(fmt_t $((SECONDS - w0)))" "$N" 2>/dev/null || true
    elif (( got != last )); then say "   online on GitHub: ${got}/${COUNT}"; last=$got; fi
    if (( got >= COUNT || SECONDS >= end )); then break; fi
    sleep 5
  done
  if [[ -t 1 ]]; then printf '\r\033[K' 2>/dev/null || true; fi
  if (( got >= COUNT )); then
    ok "${got}/${COUNT} runners online"
  else
    EXIT_CODE=2
    warn "only ${got}/${COUNT} online after 5 min. Container logs of the stragglers:"
    for i in $(seq 1 "$COUNT"); do
      if [[ $(gh_field "${HOST_SHORT}-$i" 2) != online ]]; then
        say "   ${D}--- ${PREFIX}-$i ---${N}"
        { docker logs --tail 15 "${PREFIX}-$i" 2>&1 | sed 's/^/   | /'; } || true
      fi
    done
  fi

  # 14 ------------------------------------------------------------ cleanup
  step "Cleanup + summary"
  run_soft apt_get -y autoremove --purge || true
  run_soft apt-get clean || true
  run_soft docker image prune -f || true
  save_conf
  say ""
  say "   ${B}Runners${N}"
  for i in $(seq 1 "$COUNT"); do
    c="${PREFIX}-$i"
    say "   $(printf '%-22s' "${HOST_SHORT}-$i") docker: $(docker inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' "$c" 2>/dev/null || echo missing)   github: $(gh_field "${HOST_SHORT}-$i" 2 | sed 's/^$/unknown/')"
  done
  say ""
  say "   workflow:  runs-on: [self-hosted, linux, ${LABELS_EXTRA%%,*}]"
  say "   status:    sudo ./tms-runners.sh status        logs: sudo ./tms-runners.sh logs 1"
  say "   scale:     sudo ./tms-runners.sh -n 6          teardown: sudo ./tms-runners.sh down   ${D}(before deleting the VM)${N}"
  say "   ${D}Total time $(fmt_t $((SECONDS - T0))). Runners + heal timer survive reboots. Never use these on public repos.${N}"
  if [[ -f /var/run/reboot-required ]]; then
    if (( AUTO_REBOOT == 1 )); then
      warn "kernel/OS update needs a reboot — rebooting in 15 s (runners restart by themselves)"; sleep 15; systemctl reboot
    else
      warn "a reboot is pending (kernel/OS update). Run 'sudo reboot' when idle, or use --auto-reboot. Runners restart by themselves."
    fi
  fi
  exit "$EXIT_CODE"
}

# ============================= OTHER COMMANDS ================================
require_target() { [[ -n $TARGET ]] || die "no saved config — run 'up' first or pass --org/--repo"; }
lock_or_die() {
  exec 9>"$LOCK"
  flock -n 9 || die "another tms-runners run is active (or an interrupted step is still finishing). Wait and retry."
}

cmd_status() {
  require_target
  say "${B}Containers${N}"
  docker ps -a --filter "name=^${PREFIX}-" --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' || true
  if has_env_token || gh auth status --hostname github.com >/dev/null 2>&1; then
    say ""; say "${B}GitHub (${TARGET_KIND} ${TARGET})${N}"
    load_gh_runners
    if (( GH_OK == 1 )); then
      awk -F'\t' -v p="${HOST_SHORT}-" 'index($1,p)==1{printf "  %-24s %-8s %-5s labels: %s\n",$1,$2,($3=="true"?"busy":"idle"),$4}' <<<"$GH_LIST"
    else say "  (API call failed)"; fi
  else
    say ""; say "(gh not logged in — GitHub-side status skipped; export GH_TOKEN or run 'up --keep-login')"
  fi
  say ""; say "${B}Host${N}  $(mem_mb) MB RAM, $(free_gb) GB free disk, load: $(cut -d' ' -f1-3 /proc/loadavg)"
}

cmd_logs() { docker logs -f --tail 100 "${PREFIX}-${LOGN}"; }

cmd_heal() { /usr/local/sbin/tms-runners-heal && say "heal pass done"; }

cmd_down() {
  lock_or_die
  require_target
  command -v docker >/dev/null || die "docker not installed"
  command -v gh >/dev/null || die "gh not installed"
  say "${B}Tearing down runners for ${TARGET_KIND} ${TARGET}${N}"
  do_auth
  local idx=() i
  mapfile -t idx < <(existing_indexes)
  if (( ${#idx[@]} == 0 )); then say "   no runner containers found"; fi
  for i in "${idx[@]}"; do
    say "   removing ${PREFIX}-$i (stop → delete container + volumes → deregister from GitHub)"
    remove_one "$i"
  done
  systemctl disable --now tms-runners-heal.timer >/dev/null 2>&1 || true
  if (( PURGE == 1 )); then docker rmi -f "$IMAGE" >/dev/null 2>&1 || true; say "   image removed"; fi
  rm -f "/etc/cron.daily/${APP}-prune" "$CONF"
  say "${G}✔ All runners deregistered and removed. Safe to terminate the VM.${N}"
}

case $CMD in
  up)     lock_or_die; cmd_up ;;
  status) cmd_status ;;
  logs)   cmd_logs ;;
  heal)   cmd_heal ;;
  down)   cmd_down ;;
esac
