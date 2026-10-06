function mask --description 'Run a command and mask sensitive values in its output'
    $argv | sed -E -f ~/.config/dotfiles/mask.sed
end
