# Env, PATH and abbreviations generated from config.yaml (see ./install.sh).
for file in ~/.config/dotfiles/env.fish ~/.config/dotfiles/abbr.fish
    test -r $file; and source $file
end

# mise puts the tools used below on PATH; shims suffice for non-interactive shells.
if command -q mise
    if status is-interactive
        mise activate fish | source
    else
        mise activate fish --shims | source
    end
end
