# Interactive bash setup, sourced from ~/.bashrc by the dotfiles-managed block.

HISTSIZE=50000
HISTFILESIZE=50000
HISTCONTROL=ignoreboth:erasedups
shopt -s histappend checkwinsize autocd cdspell globstar

bind '"\C-h": backward-kill-word'      # Ctrl+Backspace
bind '"\e[A": history-search-backward' # Up/Down search history by typed prefix
bind '"\e[B": history-search-forward'
bind 'set completion-ignore-case on'
bind 'set show-all-if-ambiguous on'

. "$HOME/.config/shell/common.sh"

# Built-in prompt (no Starship): [user@host] ~/path (branch) ❯
# The ❯ turns red after a failed command; user@host only shows over SSH.
if [ "$DOTFILES_PROMPT" = builtin ]; then
  [ -r /usr/lib/git-core/git-sh-prompt ] && . /usr/lib/git-core/git-sh-prompt
  # shellcheck disable=SC2034 # read by __git_ps1
  GIT_PS1_SHOWDIRTYSTATE=1
  __dotfiles_prompt() {
    local status=$? host="" git="" color=32
    [ -n "${SSH_CONNECTION:-}" ] && host='\[\e[33m\]\u@\h\[\e[0m\] '
    declare -F __git_ps1 >/dev/null && git="$(__git_ps1 ' \[\e[35m\](%s)\[\e[0m\]')"
    [ "$status" -ne 0 ] && color=31
    PS1="${host}\[\e[34m\]\w\[\e[0m\]${git} \[\e[${color}m\]❯\[\e[0m\] "
    return "$status"
  }
  PROMPT_COMMAND="__dotfiles_prompt${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
fi
