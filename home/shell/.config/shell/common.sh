# shellcheck shell=sh
# Shared by bash and zsh (sourced from their init files). Keep this POSIX.
# Fish has its equivalents in ~/.config/fish/conf.d/10-interactive.fish.

_dotfiles="$HOME/.config/dotfiles"
[ -r "$_dotfiles/env.sh" ] && . "$_dotfiles/env.sh"

# Tool integrations. mise goes first: it puts the tools below on PATH.
if [ -n "${ZSH_VERSION:-}" ]; then _sh=zsh; else _sh=bash; fi
command -v mise >/dev/null 2>&1 && eval "$(mise activate "$_sh")"
command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init "$_sh")"
command -v fzf >/dev/null 2>&1 && eval "$(fzf "--$_sh" 2>/dev/null)"
# Prompt: Starship if installed, unless `prompt: builtin` in config.yaml. Otherwise
# bash/zsh init files set up a built-in prompt.
if [ "${DOTFILES_PROMPT:-starship}" = starship ] && command -v starship >/dev/null 2>&1; then
  eval "$(starship init "$_sh")"
else
  DOTFILES_PROMPT=builtin
fi

# Better defaults, using modern tools when they're installed (see `tools`).
if command -v eza >/dev/null 2>&1; then
  alias ls='eza --group-directories-first'
  alias ll='eza -l --git --group-directories-first'
  alias la='eza -la --git --group-directories-first'
  alias lt='eza --tree --level=2 --group-directories-first'
else
  alias ls='ls --color=auto'
  alias ll='ls -lh'
  alias la='ls -lAh'
fi
command -v bat >/dev/null 2>&1 && alias cat='bat --paging=never --style=plain'
# Debian/Ubuntu ship fd and bat under other names.
command -v fd >/dev/null 2>&1 || { command -v fdfind >/dev/null 2>&1 && alias fd=fdfind; }
command -v bat >/dev/null 2>&1 || { command -v batcat >/dev/null 2>&1 && alias bat=batcat; }
alias grep='grep --color=auto'
alias ip='ip -color=auto'
alias df='df -h'
alias du='du -h'
alias free='free -h'

mkcd() { mkdir -p -- "$1" && cd -- "$1" || return; }

# up [N]: go up N directories (default 1).
up() {
  _up=""
  _n="${1:-1}"
  while [ "$_n" -gt 0 ]; do
    _up="../$_up"
    _n=$((_n - 1))
  done
  cd -- "$_up" || return
  unset _up _n
}

# Run a command and mask sensitive values in its output (rules: `mask` in config.yaml).
mask() { "$@" | sed -E -f "$HOME/.config/dotfiles/mask.sed"; }

# Aliases from config.yaml last, so they override the defaults above.
[ -r "$_dotfiles/aliases.sh" ] && . "$_dotfiles/aliases.sh"
unset _dotfiles _sh
