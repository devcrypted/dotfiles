#!/usr/bin/env bash
# Bootstrap: make sure git, Python >= 3.11 and PyYAML exist, then hand over to dotkit.
#
#   ./install.sh [apply|plan|status] [options]      # from a clone
#   bash <(curl -fsSL <raw-url>/install.sh)         # fresh machine: clones first
#
# All real work lives in dotkit/ (Python); see README.md.
set -euo pipefail

REPO_URL="${DOTFILES_REPO:-https://github.com/devcrypted/dotfiles.git}"
CLONE_DIR="${DOTFILES_DIR:-$HOME/dotfiles}"

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

as_root() { if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi; }

[[ -r /etc/debian_version ]] || die "only Debian/Ubuntu-based systems are supported"
[[ $EUID -ne 0 || -z "${SUDO_USER:-}" ]] || die "run as your normal user, not with sudo"

missing=()
command -v git >/dev/null || missing+=(git)
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  missing+=(python3)
fi
python3 -c 'import yaml' 2>/dev/null || missing+=(python3-yaml)
if ((${#missing[@]})); then
  echo "Installing bootstrap packages: ${missing[*]}"
  as_root apt-get update -qq
  as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}" >/dev/null
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' ||
    die "Python 3.11+ is required (Debian 12 / Ubuntu 24.04 or newer)"
fi

# Run from the clone this script lives in; when piped from curl, clone first.
here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [[ -n "$here" && -f "$here/dotkit/__main__.py" ]]; then
  repo="$here"
else
  [[ -d "$CLONE_DIR/.git" ]] || git clone "$REPO_URL" "$CLONE_DIR"
  repo="$CLONE_DIR"
fi

PYTHONPATH="$repo${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m dotkit "$@"
