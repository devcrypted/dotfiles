# Interactive zsh setup, sourced from ~/.zshrc by the dotfiles-managed block.

HISTFILE="$HOME/.zsh_history"
HISTSIZE=50000
SAVEHIST=50000
setopt extended_history hist_ignore_all_dups hist_ignore_space share_history
setopt auto_cd auto_pushd pushd_ignore_dups interactive_comments no_beep

# Keys: emacs mode plus the usual Ctrl/Home/End/Delete sequences.
bindkey -e
bindkey '^H' backward-kill-word       # Ctrl+Backspace
bindkey '^[[1;5C' forward-word        # Ctrl+Right
bindkey '^[[1;5D' backward-word       # Ctrl+Left
bindkey '^[[H' beginning-of-line
bindkey '^[[F' end-of-line
bindkey '^[[3~' delete-char
autoload -Uz up-line-or-beginning-search down-line-or-beginning-search
zle -N up-line-or-beginning-search
zle -N down-line-or-beginning-search
bindkey '^[[A' up-line-or-beginning-search    # Up/Down search history by typed prefix
bindkey '^[[B' down-line-or-beginning-search

# Completion. The full security audit runs at most once a day; otherwise the cached
# dump is trusted, which keeps startup fast.
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
autoload -Uz compinit
() {
  setopt local_options extended_glob
  if [[ -n $HOME/.zcompdump(#qN.mh+24) || ! -e $HOME/.zcompdump ]]; then
    compinit
  else
    compinit -C
  fi
}

source "$HOME/.config/shell/common.sh"

# Built-in prompt (no Starship): [user@host] ~/path (branch) ❯
# The ❯ turns red after a failed command; user@host only shows over SSH.
if [[ $DOTFILES_PROMPT == builtin ]]; then
  autoload -Uz vcs_info
  zstyle ':vcs_info:git:*' formats ' %F{magenta}(%b)%f'
  zstyle ':vcs_info:git:*' actionformats ' %F{magenta}(%b|%a)%f'
  precmd_functions+=(vcs_info)
  setopt prompt_subst
  PROMPT='${SSH_CONNECTION:+%F{yellow}%n@%m%f }%F{blue}%~%f${vcs_info_msg_0_} %(?.%F{green}.%F{red})❯%f '
fi

# Plugins from apt; syntax highlighting must be sourced last.
for plugin in zsh-autosuggestions zsh-syntax-highlighting; do
  [[ -r /usr/share/$plugin/$plugin.zsh ]] && source "/usr/share/$plugin/$plugin.zsh"
done
unset plugin
