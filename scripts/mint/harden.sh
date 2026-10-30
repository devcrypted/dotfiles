#!/usr/bin/env bash
# Debloat, clean and harden a Linux Mint (Cinnamon) desktop.
#
#   scripts/mint/harden.sh                    # preview: prints what would change, changes nothing
#   scripts/mint/harden.sh --apply            # do it (asks for sudo once)
#   scripts/mint/harden.sh --apply --aggressive
#   scripts/mint/harden.sh --apply --only firewall,kernel
#   scripts/mint/harden.sh --apply --skip debloat
#
# Run as your normal user; it uses sudo where needed. Safe to rerun: each step checks
# first. Take a Timeshift snapshot before the first --apply (`sudo timeshift --create`).
#
# Sections (default order):
#   debloat    purge preinstalled apps you don't use (lists below). Every removal is
#              simulated first and skipped if apt would take Mint/Cinnamon with it.
#   telemetry  purge crash reporters (whoopsie, apport, kerneloops) and Ubuntu reporting.
#   services   stop network discovery you don't need (cups-browsed; aggressive: avahi,
#              ModemManager without a modem); harden sshd if installed.
#   firewall   ufw: deny incoming, allow outgoing (SSH rate-limited if sshd runs).
#   kernel     sysctl hardening (/etc/sysctl.d/60-dotfiles-hardening.conf), no core dumps.
#   updates    automatic updates and autoremove via mintupdate-automation; AppArmor on.
#   desktop    no autorun of media, lock on suspend, no guest login.
#   cleanup    autoremove, leftover configs, apt cache, journal capped at 200 MB,
#              unused flatpak runtimes, old thumbnails/trash/crash dumps.
#
# --aggressive also: removes LibreOffice, Firefox (only when another browser is
# installed), Celluloid, Pix, Drawing, printing/scanning tools when no printer is set
# up; turns off avahi, NetworkManager's connectivity check, recent-file history and
# randomises Wi-Fi MAC addresses per network.
set -euo pipefail

# --- What to remove: edit freely ---------------------------------------------------
BLOAT=(
  hexchat thunderbird rhythmbox hypnotix transmission-gtk transmission-common
  warpinator mintwelcome sticky webapp-manager mintchat thingy onboard orca
  brltty # braille display daemon; also grabs USB-serial adapters (Arduino, ESP32)
)
BLOAT_AGGRESSIVE=(
  'libreoffice-*' celluloid pix drawing gucharmap
)
TELEMETRY=(whoopsie apport apport-gtk apport-symptoms kerneloops ubuntu-report popularity-contest)
PRINTING=(simple-scan hplip hplip-data printer-driver-hpcups system-config-printer)
# apt must never remove these as a side effect of the above.
PROTECTED='^(mint-meta-.*|cinnamon.*|nemo|muffin|xapp.*|mintupdate|mintsystem|mint-common|lightdm.*|slick-greeter|network-manager.*|xorg|xserver-xorg.*|ubuntu-minimal|ubuntu-standard|linux-image-.*|linux-generic.*|sudo|apt|systemd.*|timeshift|flatpak|pipewire.*|pulseaudio.*)$'

SECTIONS=(debloat telemetry services firewall kernel updates desktop cleanup)

APPLY=0 AGGRESSIVE=0 YES=0 ONLY="" SKIP=""
usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; }
while (($#)); do
  case "$1" in
    --apply) APPLY=1 ;;
    --aggressive) AGGRESSIVE=1 ;;
    -y | --yes) YES=1 ;;
    --only) ONLY="$2" && shift ;;
    --skip) SKIP="$2" && shift ;;
    -h | --help) usage && exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2 && exit 2 ;;
  esac
  shift
done

# --- Helpers --------------------------------------------------------------------------
bold=$'\e[1m' dim=$'\e[2m' green=$'\e[32m' yellow=$'\e[33m' reset=$'\e[0m'
[[ -t 1 ]] || bold="" dim="" green="" yellow="" reset=""
section() { printf '\n%s== %s ==%s\n' "$bold" "$1" "$reset"; }
info() { printf '  %s\n' "$*"; }
skip() { printf '  %s%s%s\n' "$dim" "$*" "$reset"; }
warn() { printf '  %s! %s%s\n' "$yellow" "$*" "$reset"; }
changed=0
# change <description> <command...>: run (or, in preview, print) a change.
change() {
  local what="$1"
  shift
  changed=$((changed + 1))
  if ((APPLY)); then
    printf '  %s+%s %s\n' "$green" "$reset" "$what"
    "$@"
  else
    printf '  %s~%s %s %s(preview)%s\n' "$yellow" "$reset" "$what" "$dim" "$reset"
  fi
}
as_root() { sudo "$@"; }
on_apply() { if ((APPLY)); then "$@"; fi; } # follow-up step of a change just made
installed() { dpkg-query -W -f='${db:Status-Abbrev}' "$1" 2>/dev/null | grep -q '^ii'; }
# installed_matching PATTERN...: installed package names matching apt globs.
installed_matching() {
  local p
  for p in "$@"; do
    dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' "$p" 2>/dev/null | awk '/^ii/{print $2}'
  done | sort -u
}
tee_root() { sudo mkdir -p "${1%/*}" && printf '%s\n' "$2" | sudo tee "$1" >/dev/null; }
purge_residual() { dpkg -l | awk '/^rc/{print $2}' | xargs -r sudo dpkg --purge >/dev/null; }
# write_root_file PATH CONTENT: install a root-owned file only when it differs.
# Returns 0 when it (would) write, so `if write_root_file ...; then reload; fi`.
write_root_file() {
  local path="$1" content="$2"
  if [[ -f "$path" ]] && [[ "$(cat "$path")" == "$content" ]]; then
    skip "$path is up to date"
    return 1
  fi
  change "write $path" tee_root "$path" "$content"
}
want() {
  local s="$1"
  [[ -z "$ONLY" || ",$ONLY," == *",$s,"* ]] && [[ ",$SKIP," != *",$s,"* ]]
}
# purge PKG...: purge the installed ones, skipping any whose removal drags in protected packages.
purge() {
  local pkgs=() pkg extra
  for pkg in $(installed_matching "$@"); do
    extra="$(apt-get -s purge "$pkg" 2>/dev/null | awk '/^(Purg|Remv) /{print $2}' | grep -Ev "^${pkg}$" || true)"
    if grep -Eq "$PROTECTED" <<<"$extra"; then
      warn "keeping $pkg: removing it would also remove $(grep -E "$PROTECTED" <<<"$extra" | paste -sd' ')"
      continue
    fi
    pkgs+=("$pkg")
  done
  if ((${#pkgs[@]})); then
    change "purge ${pkgs[*]}" as_root env DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq "${pkgs[@]}"
  else
    skip "nothing to remove"
  fi
}
service_off() {
  local unit="$1" state
  state="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
  if [[ -n "$state" && "$state" != masked && "$state" != not-found ]]; then
    change "stop and mask $unit" as_root systemctl disable --now --quiet "$unit"
    on_apply as_root systemctl mask --quiet "$unit"
  else
    skip "$unit is off or not installed"
  fi
}
gset() { # gset SCHEMA KEY VALUE: user desktop setting, only when different
  local cur
  cur="$(gsettings get "$1" "$2" 2>/dev/null)" || return 0
  [[ "$cur" == "$3" ]] && skip "$1 $2 already $3" && return 0
  change "set $1 $2 = $3" gsettings set "$1" "$2" "$3"
}

# --- Preconditions --------------------------------------------------------------------
[[ $EUID -ne 0 ]] || {
  echo "run as your normal user (it uses sudo itself)" >&2
  exit 1
}
. /etc/os-release
[[ "${ID:-}" == linuxmint ]] || {
  echo "this script is for Linux Mint (found ${PRETTY_NAME:-unknown})" >&2
  exit 1
}
printf '%sLinux Mint hardening%s  %s · %s%s\n' "$bold" "$reset" "$PRETTY_NAME" \
  "$( ((APPLY)) && echo apply || echo 'preview (nothing changes; add --apply)')" \
  "$( ((AGGRESSIVE)) && echo ' · aggressive')"
if ((APPLY)); then
  if ((! YES)); then
    read -rp "Changes will be made. Took a Timeshift snapshot? Continue? [y/N] " answer
    [[ "$answer" == [yY]* ]] || exit 1
  fi
  sudo -v
fi

# --- Sections -------------------------------------------------------------------------
s_debloat() {
  local list=("${BLOAT[@]}")
  if ((AGGRESSIVE)); then
    list+=("${BLOAT_AGGRESSIVE[@]}")
    # Firefox only goes when another browser can take over.
    if command -v brave-browser >/dev/null || command -v google-chrome >/dev/null || command -v chromium >/dev/null; then
      list+=(firefox firefox-locale-en)
    else
      skip "keeping firefox: no other browser installed"
    fi
    if [[ -z "$(lpstat -e 2>/dev/null)" ]]; then list+=("${PRINTING[@]}"); else skip "keeping printing tools: a printer is set up"; fi
  fi
  purge "${list[@]}"
}

s_telemetry() {
  purge "${TELEMETRY[@]}"
  [[ -f /etc/default/motd-news ]] && grep -q '^ENABLED=1' /etc/default/motd-news &&
    change "turn off motd-news" as_root sed -i 's/^ENABLED=1/ENABLED=0/' /etc/default/motd-news
  return 0
}

s_services() {
  service_off cups-browsed # adds printers announced on the network (CVE-2024-47176 class)
  if ((AGGRESSIVE)); then
    service_off avahi-daemon # mDNS/zeroconf: AirPlay, network printer and share discovery
    if ! compgen -G '/dev/cdc-wdm*' >/dev/null && ! compgen -G '/sys/class/net/ww*' >/dev/null; then
      service_off ModemManager
    fi
  fi
  if systemctl is-active --quiet ssh; then
    local keys="$HOME/.ssh/authorized_keys" pw="yes"
    if [[ -s "$keys" ]]; then pw="no"; else warn "sshd keeps password logins: $keys is empty"; fi
    if write_root_file /etc/ssh/sshd_config.d/60-dotfiles-hardening.conf "# Managed by dotfiles scripts/mint/harden.sh
PermitRootLogin no
PasswordAuthentication $pw
KbdInteractiveAuthentication no
PermitEmptyPasswords no
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowTcpForwarding local
ClientAliveInterval 300
ClientAliveCountMax 2"; then on_apply sudo bash -c "sshd -t && systemctl reload ssh"; fi
  fi
  return 0
}

s_firewall() {
  # ufw keeps its state in world-readable files, so the preview needs no sudo.
  if installed ufw && grep -q '^ENABLED=yes' /etc/ufw/ufw.conf &&
    grep -q '^DEFAULT_INPUT_POLICY="DROP"' /etc/default/ufw; then
    skip "ufw is on and denies incoming"
  else
    installed ufw || change "install ufw" as_root apt-get install -y -qq ufw
    change "ufw: deny incoming, allow outgoing" as_root ufw default deny incoming
    on_apply as_root ufw default allow outgoing
    if systemctl is-active --quiet ssh; then
      change "ufw: allow SSH (rate-limited)" as_root ufw limit OpenSSH
    fi
    change "enable ufw" as_root ufw --force enable
  fi
  if command -v docker >/dev/null; then
    info "note: ports published by Docker (-p) bypass ufw; bind them to 127.0.0.1 unless public"
  fi
}

s_kernel() {
  if write_root_file /etc/sysctl.d/60-dotfiles-hardening.conf "# Managed by dotfiles scripts/mint/harden.sh
# Hide kernel pointers and logs from unprivileged users.
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
kernel.printk = 3 3 3 3
# No unprivileged eBPF; harden the BPF JIT; no kexec into another kernel.
kernel.unprivileged_bpf_disabled = 1
net.core.bpf_jit_harden = 2
kernel.kexec_load_disabled = 1
# Only parents may ptrace (debuggers still work on their own children / with sudo).
kernel.yama.ptrace_scope = 1
kernel.perf_event_paranoid = 2
dev.tty.ldisc_autoload = 0
vm.unprivileged_userfaultfd = 0
# Filesystem: block symlink/hardlink/FIFO tricks in sticky dirs like /tmp.
fs.protected_symlinks = 1
fs.protected_hardlinks = 1
fs.protected_fifos = 2
fs.protected_regular = 2
fs.suid_dumpable = 0
# Network: no redirects or source routing, anti-spoofing, SYN flood protection.
# rp_filter = 1 can break asymmetric routing (some VPNs); set 2 there.
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.default.secure_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv6.conf.default.accept_source_route = 0
net.ipv4.conf.all.log_martians = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_rfc1337 = 1"; then on_apply as_root sysctl --system -q; fi
  write_root_file /etc/security/limits.d/60-dotfiles-nocore.conf "# Managed by dotfiles scripts/mint/harden.sh: no core dumps (they can hold secrets)
* hard core 0" || true
  write_root_file /etc/systemd/coredump.conf.d/60-dotfiles.conf "# Managed by dotfiles scripts/mint/harden.sh
[Coredump]
Storage=none
ProcessSizeMax=0" || true
  return 0
}

s_updates() {
  if command -v mintupdate-automation >/dev/null; then
    [[ -e /var/lib/linuxmint/mintupdate-automatic-upgrades-enabled ]] ||
      change "turn on automatic updates" as_root mintupdate-automation upgrade enable
    [[ -e /var/lib/linuxmint/mintupdate-automatic-removals-enabled ]] ||
      change "turn on automatic removal of old kernels" as_root mintupdate-automation autoremove enable
  fi
  if command -v aa-enabled >/dev/null && [[ "$(aa-enabled 2>/dev/null)" == Yes ]]; then
    skip "AppArmor is enabled"
  else
    warn "AppArmor is not enabled: check the apparmor package and kernel command line"
  fi
}

s_desktop() {
  gset org.cinnamon.desktop.media-handling autorun-never true
  gset org.cinnamon.desktop.screensaver lock-enabled true
  gset org.cinnamon.settings-daemon.plugins.power lock-on-suspend true
  if ((AGGRESSIVE)); then
    gset org.cinnamon.desktop.privacy remember-recent-files false
    if write_root_file /etc/NetworkManager/conf.d/60-dotfiles-privacy.conf "# Managed by dotfiles scripts/mint/harden.sh
# No phoning home to check for a captive portal.
[connectivity]
enabled=false

# A random MAC per Wi-Fi network (stable for that network), random while scanning.
[device]
wifi.scan-rand-mac-address=yes

[connection]
wifi.cloned-mac-address=stable"; then on_apply as_root systemctl reload NetworkManager; fi
  fi
  if [[ -d /etc/lightdm/lightdm.conf.d ]]; then
    write_root_file /etc/lightdm/lightdm.conf.d/60-dotfiles.conf "# Managed by dotfiles scripts/mint/harden.sh
[Seat:*]
allow-guest=false" || true
  fi
  if [[ -d "$HOME/.local/kitty.app" ]]; then
    info "note: ~/.local/kitty.app is an old Kitty install; delete it if you no longer use it"
  fi
}

s_cleanup() {
  local auto residual
  auto="$(apt-get -s autoremove --purge 2>/dev/null | awk '/^(Purg|Remv) /{print $2}')"
  if grep -Eq "$PROTECTED" <<<"$auto"; then
    warn "skipping autoremove: it would remove $(grep -E "$PROTECTED" <<<"$auto" | paste -sd' ')"
  elif [[ -n "$auto" ]]; then
    change "autoremove $(wc -l <<<"$auto") unused package(s)" as_root apt-get autoremove --purge -y -qq
  fi
  residual="$(dpkg -l | awk '/^rc/{print $2}')"
  [[ -z "$residual" ]] || change "purge leftover configs of $(wc -l <<<"$residual") removed package(s)" \
    purge_residual
  change "clear the apt download cache" as_root apt-get clean
  if write_root_file /etc/systemd/journald.conf.d/60-dotfiles.conf "# Managed by dotfiles scripts/mint/harden.sh
[Journal]
SystemMaxUse=200M
MaxRetentionSec=1month"; then on_apply as_root systemctl restart systemd-journald; fi
  change "trim the journal to 200 MB" as_root journalctl --vacuum-size=200M -q
  if command -v flatpak >/dev/null; then change "remove unused flatpak runtimes" flatpak uninstall --unused -y --noninteractive; fi
  if compgen -G '/var/crash/*' >/dev/null; then change "delete crash dumps in /var/crash" as_root find /var/crash -mindepth 1 -delete; fi
  local old=()
  for dir in "$HOME/.cache/thumbnails" "$HOME/.local/share/Trash"; do [[ -d "$dir" ]] && old+=("$dir"); done
  if ((${#old[@]})) && [[ -n "$(find "${old[@]}" -mindepth 2 -type f -mtime +30 -print -quit)" ]]; then
    change "delete thumbnails and trash older than 30 days" find "${old[@]}" -mindepth 2 -type f -mtime +30 -delete
  fi
}

for s in "${SECTIONS[@]}"; do
  want "$s" || continue
  section "$s"
  "s_$s"
done

echo
if ((APPLY)); then
  echo "${green}Done.${reset} Reboot to load every kernel and service change."
else
  echo "Preview only: $changed change(s) listed. Run again with --apply to make them."
fi
