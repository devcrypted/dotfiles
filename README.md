# INTRODUCTION

This is dotfiles repo which contains custom configs related to my Fedora OS installed on my Desktop. This can be reused using GNU Stow tool to quickly create dotfiles.

## Prerequisites

1. Run `dnf udpate && dnf upgrade -y && dnf install git ansible stow -y`

## How to Backup (Add to GIT and Stow)

1. Copy Any dotfile from user home (~) to dotfiles folder. E.g. `cp ~/.zshrc ~/dotfiles/.zshrc`
2. Stow add `stow . --dotfiles --adopt`
3. CD to dotfiles directory `cd ~/dotfiles`
4. Git Add `git add .`
5. Git Commit `git commit -m 'Added .zshrc dotfile'`
6. Git Push `git push origin main`


## How to Restore

1. Git Clone `git clone git@github.com:aworkaround/dotfiles.git -b main ~/dotfiles`
2. CD to Dotfiles `cd ~/dotfiles`
3. CAUTION: This command will replace your existing dotfiles in $HOME. Stow add `stow . --dotfiles --adopt`. Use it without `--adopt` if you're not sure.


## How to Install Apps

1. Run `ansible-playbook ~/.bootstrap/setup.yaml --ask-become-pass` to install everything required.

## Considerations

- If you want to ignore any dotfile to be commited in Git, add it to `.gitignore` file.
- If you want to ignore any dotfile to become symlink by Stow, add it to `.stow-local-ignore` file.
- Don't store any secrets, keys, tokens, and SSH RSA keys to this repo for security.
