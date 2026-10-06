# Built-in prompt (no Starship): [user@host] ~/path (branch) ❯
# The ❯ turns red after a failed command; user@host only shows over SSH.
function fish_prompt
    set -l last $status
    set -q SSH_CONNECTION; and printf '%s%s@%s%s ' (set_color yellow) $USER (prompt_hostname) (set_color normal)
    printf '%s%s%s' (set_color blue) (prompt_pwd) (set_color normal)
    printf '%s%s%s' (set_color magenta) (fish_vcs_prompt) (set_color normal)
    test $last -eq 0; and set_color green; or set_color red
    printf ' ❯ '
    set_color normal
end
