status is-interactive; or return

set -g fish_greeting

command -q zoxide; and zoxide init fish | source
command -q fzf; and fzf --fish 2>/dev/null | source
# Starship replaces the built-in functions/fish_prompt.fish unless `prompt: builtin`.
if test "$DOTFILES_PROMPT" != builtin; and command -q starship
    starship init fish | source
end

# Better defaults, using modern tools when they're installed (see `tools`).
# Fish already colours ls and defines ll/la; eza upgrades them.
if command -q eza
    alias ls 'eza --group-directories-first'
    alias ll 'eza -l --git --group-directories-first'
    alias la 'eza -la --git --group-directories-first'
    alias lt 'eza --tree --level=2 --group-directories-first'
end
command -q bat; and alias cat 'bat --paging=never --style=plain'
# Debian/Ubuntu ship fd and bat under other names.
not command -q fd; and command -q fdfind; and alias fd fdfind
not command -q bat; and command -q batcat; and alias bat batcat
alias ip 'ip -color=auto'
alias df 'df -h'
alias du 'du -h'
alias free 'free -h'
