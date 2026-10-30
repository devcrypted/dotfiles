#!/usr/bin/env bash
# Save this machine's Cinnamon look and feel into the repo (desktop/cinnamon/), so the
# `cinnamon` task can apply it on other Linux Mint machines.
#
#   scripts/mint/cinnamon-capture.sh      # then: git diff desktop/cinnamon
#
# Captured: panels and applets, themes, icons, cursor, fonts, keyboard shortcuts,
# gestures, window manager, Nemo, Xed, Mint Update preferences, and each applet's
# settings (~/.config/cinnamon/spices). Left out: window sizes, recent-file state,
# night-light coordinates (your location) and device IDs.
#
# It also lists the Spices applets and themes installed in your home folder; copy
# the ones you want into `cinnamon.applets` / `cinnamon.themes` in config.yaml.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
out="$repo/desktop/cinnamon"

command -v dconf >/dev/null || {
  echo "error: dconf not found (sudo apt install dconf-cli)" >&2
  exit 1
}

# dconf paths to save.
PATHS=(
  /org/cinnamon/
  /org/nemo/
  /org/x/apps/portal/
  /org/x/editor/preferences/
  /org/x/editor/plugins/
  /org/gnome/desktop/privacy/
  /com/linuxmint/updates/
)
# Full key paths (ERE) never saved: window state, timestamps, location, device IDs.
SKIP='^/org/cinnamon/(panel-edit-mode|settings-daemon/plugins/color/night-light-last-coordinates)$'
SKIP+='|^/org/nemo/window-state/'
SKIP+='|^/org/x/editor/plugins/filebrowser/'
SKIP+='|^/com/linuxmint/updates/(window-.*|.*-last-run)$'
SKIP+='|connect-id$|/(geometry|maximized|size|state)$'
# GTK apps outside Cinnamon read these; only the look is worth keeping.
GNOME_INTERFACE=(gtk-theme icon-theme cursor-theme cursor-size font-name color-scheme)

# Print `dconf dump PATH` with absolute section names, minus skipped keys.
dump() {
  dconf dump "$1" | awk -v base="${1%/}" -v skip="$SKIP" '
    /^\[/ {
      sec = substr($0, 2, length($0) - 2)
      full = (sec == "/") ? base : base "/" sec
      pending = 1
      next
    }
    /^$/ { next }
    {
      key = substr($0, 1, index($0, "=") - 1)
      if ((full "/" key) ~ skip) next
      if (pending) { printf "\n[%s]\n", substr(full, 2); pending = 0 }
      print
    }'
}

mkdir -p "$out"
{
  echo "# Cinnamon settings for \`dconf load /\`, applied by the cinnamon task."
  echo "# Regenerate with scripts/mint/cinnamon-capture.sh; edits by hand are fine too."
  for path in "${PATHS[@]}"; do dump "$path"; done
  echo
  echo "[org/gnome/desktop/interface]"
  for key in "${GNOME_INTERFACE[@]}"; do
    value="$(dconf read "/org/gnome/desktop/interface/$key")"
    [[ -z "$value" ]] || echo "$key=$value"
  done
} >"$out/dconf.ini"
echo "saved ${out#"$repo"/}/dconf.ini ($(grep -c '=' "$out/dconf.ini") settings)"

# Applet settings. Numbered files belong to one applet instance (the number is its id
# in enabled-applets), so a stale set is replaced rather than merged.
rm -rf "$out/spices"
spices="$HOME/.config/cinnamon/spices"
if [[ -d "$spices" ]]; then
  while IFS= read -r -d '' file; do
    rel="${file#"$spices"/}"
    mkdir -p "$out/spices/$(dirname "$rel")"
    cp "$file" "$out/spices/$rel"
    [[ -z "$(tail -c1 "$out/spices/$rel")" ]] || echo >>"$out/spices/$rel" # end-of-file hook wants one
  done < <(find "$spices" -name '*.json' -type f -print0)
  echo "saved ${out#"$repo"/}/spices/ ($(find "$out/spices" -name '*.json' | wc -l) applet settings files)"
fi

list() { [[ -d "$1" ]] && find "$1" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | paste -sd, - | sed 's/,/, /g'; }
echo
echo "Installed in your home folder (for config.yaml):"
echo "  cinnamon.applets: [$(list "$HOME/.local/share/cinnamon/applets")]"
echo "  cinnamon.themes:  [$(list "$HOME/.themes")]"
