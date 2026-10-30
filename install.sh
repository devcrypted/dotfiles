#!/usr/bin/env bash
# Bootstrap: make sure git, Python >= 3.11 and PyYAML exist, then hand over to dotkit.
#
#   ./install.sh [apply|plan|status] [options]      # from a clone
#   curl -fsSL https://dot.kamal.sh | bash          # fresh machine: clones first
#   curl -fsSL https://dot.kamal.sh | bash -s -- plan --role server   # with arguments
#
# All real work lives in dotkit/ (Python); see README.md and USAGE.md.
set -euo pipefail

REPO_URL="${DOTFILES_REPO:-https://github.com/devcrypted/dotfiles.git}"
CLONE_DIR="${DOTFILES_DIR:-$HOME/dotfiles}"

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

as_root() { if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi; }

# Everything runs from main(), so `curl | bash` parses the whole script before running it.
main() {
  [[ -r /etc/debian_version ]] || die "only Debian/Ubuntu-based systems are supported"
  [[ $EUID -ne 0 || -z "${SUDO_USER:-}" ]] || die "run as your normal user, not with sudo"

  # The distro's Python, which is where apt installs python3-yaml. A `python3` earlier on
  # PATH (mise, pyenv, conda) usually lacks PyYAML, so only fall back to it if needed.
  PY3=/usr/bin/python3
  [[ -x "$PY3" ]] || PY3="$(command -v python3 || echo /usr/bin/python3)"

  missing=()
  command -v git >/dev/null || missing+=(git)
  if ! "$PY3" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    missing+=(python3)
  fi
  "$PY3" -c 'import yaml' 2>/dev/null || missing+=(python3-yaml)
  if ((${#missing[@]})); then
    echo "Installing bootstrap packages: ${missing[*]}"
    as_root apt-get update -qq
    as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}" >/dev/null
    PY3=/usr/bin/python3
    "$PY3" -c 'import sys; sys.exit(sys.version_info < (3, 11))' ||
      die "Python 3.11+ is required (Debian 12 / Ubuntu 24.04 or newer)"
    "$PY3" -c 'import yaml' 2>/dev/null || die "python3-yaml is installed but $PY3 can't import it"
  fi

  # Run from the clone this script lives in. Piped from curl there is no script file:
  # use (or make) the clone in $CLONE_DIR.
  here=""
  if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  fi
  if [[ -n "$here" && -f "$here/dotkit/__main__.py" ]]; then
    repo="$here"
  else
    [[ -d "$CLONE_DIR/.git" ]] || git clone "$REPO_URL" "$CLONE_DIR"
    repo="$CLONE_DIR"
  fi

  PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}" exec "$PY3" -m dotkit "$@"
}

main "$@"
