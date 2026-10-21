# claude-profile.fish
# Switch between several Claude Code logins using CLAUDE_CONFIG_DIR (fish version).
#
# Install (pick one):
#   cp claude-profile.fish ~/.config/fish/conf.d/claude-profile.fish
#   or add to ~/.config/fish/config.fish:   source ~/claude-profile.fish
#
# Usage:
#   cprof              show profiles and which are logged in
#   cprof 2            switch to profile 2 (logs in first if needed)
#   cprof use 2        same as above
#   cprof login 2      force a fresh login for profile 2
#   cprof list         list all profiles
#
# Shares ~/.claude-profiles with the bash/zsh version, so both shells agree.
# Override before sourcing: CLAUDE_PROFILES_HOME, CLAUDE_PROFILE_COUNT

set -q CLAUDE_PROFILES_HOME; or set -g CLAUDE_PROFILES_HOME $HOME/.claude-profiles
set -q CLAUDE_PROFILE_COUNT; or set -g CLAUDE_PROFILE_COUNT 3

function _cprof_dir
    echo $CLAUDE_PROFILES_HOME/profile-$argv[1]
end

function _cprof_valid
    string match -qr '^[0-9]+$' -- "$argv[1]"; or return 1
    test $argv[1] -ge 1 -a $argv[1] -le $CLAUDE_PROFILE_COUNT
end

# Linux/WSL keep the login in <dir>/.credentials.json; macOS uses the Keychain.
function _cprof_logged_in
    set -l dir $argv[1]
    if test (uname -s) = Darwin
        env CLAUDE_CONFIG_DIR=$dir claude auth status >/dev/null 2>&1
    else
        test -s $dir/.credentials.json
    end
end

function _cprof_login
    set -l n $argv[1]
    set -l dir (_cprof_dir $n)
    mkdir -p $dir; or return 1
    echo "Profile $n has no login. Starting Claude login..."
    echo "Open the link it prints in your browser, sign in, and paste the code back here if asked."
    env CLAUDE_CONFIG_DIR=$dir claude auth login; or return 1
    if not _cprof_logged_in $dir
        echo "Login for profile $n did not complete." >&2
        return 1
    end
end

function _cprof_current
    test -f $CLAUDE_PROFILES_HOME/current; and cat $CLAUDE_PROFILES_HOME/current
end

function _cprof_use
    set -l n $argv[1]
    if not _cprof_valid "$n"
        echo "Profile must be a number from 1 to $CLAUDE_PROFILE_COUNT." >&2
        return 1
    end
    set -l dir (_cprof_dir $n)
    mkdir -p $dir; or return 1
    if not _cprof_logged_in $dir
        _cprof_login $n; or return 1
    end
    echo $n >$CLAUDE_PROFILES_HOME/current
    set -gx CLAUDE_CONFIG_DIR $dir
    echo "Active Claude profile: $n ($dir)"
end

function _cprof_status
    set -l cur (_cprof_current)
    for i in (seq 1 $CLAUDE_PROFILE_COUNT)
        set -l dir (_cprof_dir $i)
        set -l state "not logged in"
        _cprof_logged_in $dir; and set state "logged in"
        set -l mark " "
        test "$i" = "$cur"; and set mark "*"
        printf '%s %s  %-14s %s\n' $mark $i $state $dir
    end
    if set -q CLAUDE_CONFIG_DIR
        echo "(* = active in new shells; this shell uses: $CLAUDE_CONFIG_DIR)"
    else
        echo "(* = active in new shells; this shell uses: default ~/.claude)"
    end
end

function cprof
    if not command -sq claude
        echo "claude CLI not found on PATH." >&2
        return 1
    end
    mkdir -p $CLAUDE_PROFILES_HOME; or return 1

    set -l cmd status
    set -q argv[1]; and set cmd $argv[1]

    if string match -qr '^[0-9]+$' -- "$cmd"
        _cprof_use $cmd
        return
    end

    switch $cmd
        case status list ls
            _cprof_status
        case use
            _cprof_use "$argv[2]"
        case login
            if not _cprof_valid "$argv[2]"
                echo "Usage: cprof login <1-$CLAUDE_PROFILE_COUNT>" >&2
                return 1
            end
            rm -f (_cprof_dir $argv[2])/.credentials.json
            _cprof_login $argv[2]
        case '*'
            echo "Usage: cprof [N | use N | login N | list]" >&2
            return 1
    end
end

# New shells restore the last chosen profile (never prompts for login).
function _cprof_restore
    set -l n (_cprof_current)
    if _cprof_valid "$n"
        set -gx CLAUDE_CONFIG_DIR (_cprof_dir $n)
    end
end
_cprof_restore
