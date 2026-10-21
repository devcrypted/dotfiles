# shellcheck shell=sh
# Run by Claude Code before every Bash command in a cloud session (CLAUDE_ENV_FILE).
# Its shell snapshot keeps aliases from ~/.bashrc but not PATH, so set PATH here.
[ -r "$HOME/.config/dotfiles/env.sh" ] && . "$HOME/.config/dotfiles/env.sh"
case ":$PATH:" in
  *":$HOME/.local/share/mise/shims:"*) ;;
  *) export PATH="$HOME/.local/share/mise/shims:$PATH" ;;
esac
