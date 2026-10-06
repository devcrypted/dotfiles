# Managing your setup

The rule: **anything you want on every machine goes into this repo**. Either as a
line in `config.yaml` (what to install) or as a file under `home/` (how it's
configured). Then commit. A new machine is just `git clone` + `./install.sh`.

## Where each change goes

| I want to… | Change | Notes |
| --- | --- | --- |
| Install a CLI tool or language runtime | `tools:` in `config.yaml` | Preferred for most dev tools. Check the [mise registry](https://mise.jdx.dev/registry.html). Removing the line uninstalls it. |
| Install a system package | `packages:` in `config.yaml` | For things from the distro archive (libraries, daemons, desktop apps). Removing the line does *not* uninstall. |
| Install from a vendor's apt repo | `apt_repos:` in `config.yaml` | Key URL, repo URL and the packages it provides. See the comment in `config.yaml`. |
| Keep a tool's config file | `./install.sh adopt ~/.config/<tool>` | Moves it into `home/<tool>/`, links it back and enables the module. |
| Edit a managed config file | Edit it in place (`~/.config/...`) | It's a symlink into the repo, so the change shows up in `git status`. |
| Add an alias, env var or PATH entry | `aliases:` / `env:` / `path:` in `config.yaml` | Applies to bash, zsh and fish. |
| Add a shell function or setting | `home/shell/.config/shell/common.sh` (bash+zsh), `home/fish/.config/fish/` (fish) | A shell-specific setting goes in `home/<shell>/`. |
| Change the login shell or prompt | `shells.default`, `prompt` in `config.yaml` | |
| Change something on one machine only | `config.local.yaml` (gitignored) | Merged over `config.yaml`; `key: null` removes a key. |
| Add a Windows app | `windows/packages.json` | Then rerun `windows/install.ps1`. |
| Automate something none of the above covers | A new task in `dotkit/tasks/` | See [Adding a task](#adding-a-task). |

After any change: `./install.sh plan` to preview, `./install.sh` to apply, then commit.

## The lifecycle of a tool

1. **Try it.** Install by hand, or add it to `tools:` / `packages:` and run
   `./install.sh`.
2. **Configure it** the normal way, wherever the tool keeps its config.
3. **Keep it.**

   ```bash
   ./install.sh adopt ~/.config/<tool>          # or a single file
   ./install.sh adopt ~/.<tool>rc --module <tool>   # outside ~/.config: name the module
   git add home/<tool> config.yaml && git commit -m "Add <tool> config"
   ```

   `adopt` warns when a file looks like it contains credentials. Keep those out
   of git (see [Secrets](#secrets)).
4. **Change it later** by editing `~/.config/<tool>/...` as usual. You're editing the
   repo copy through the symlink, so commit when happy.
5. **Retire it.** Remove it from `tools:` / `modules:` and run `./install.sh`.
   Its links are removed and its mise install is deleted. Delete `home/<tool>/` and
   commit if you don't want it back.

## A new machine

```bash
git clone https://github.com/devcrypted/dotfiles.git ~/dotfiles
cd ~/dotfiles && ./install.sh plan && ./install.sh
```

Existing files that would be replaced are moved to
`~/.local/state/dotfiles/backups/<run>/`, not deleted. Things that need a reboot
or re-login (NVIDIA driver, docker group, login shell) are listed at the end.

## What is *not* tracked here, by design

| What | Where it lives | Why |
| --- | --- | --- |
| Secrets: SSH keys, tokens, `~/.config/gh/hosts.yml`, cloud credentials | Only on the machine | Public repo. Re-authenticate on a new machine (`gh auth login`, `az login`, …). |
| Lines tools append to `~/.bashrc`, `~/.zshrc`, `~/.config/fish/config.fish`, `~/.gitconfig` | Only on the machine | These files are deliberately local. If a line matters everywhere, move it into the repo (an `env:`/`path:` entry or `home/<shell>/`). |
| Tool caches and state (`~/.cache`, `~/.local/share`, history files) | Only on the machine | Regenerated automatically. |
| Installer bookkeeping | `~/.local/state/dotfiles/state.json` | Records what this machine has applied. |

## Staying in sync

- `git status` shows edits to managed files, because they're symlinks into the repo.
- `./install.sh status` shows each task as ok or pending on this machine.
  Run it after pulling changes made on another machine.
- `./install.sh --no-once` is the quick routine sync.

## Secrets

Never commit credentials. If a tool mixes settings and secrets in one file, adopt
only the settings file, or keep the secret part in an untracked file the tool can
include (many support an `include` directive, like `~/.gitconfig` does here).

## Adding a task

For setup the config keys can't express (a desktop setting, an installer script, a
service), add a task:

1. Create `dotkit/tasks/<name>.py` with a `Task` subclass (`dotkit/tasks/ssh.py` is a
   small example). `plan()` returns the changes still needed and must not modify
   anything. Set `once = True` for one-time setup.
2. Register it in `TASKS` in `dotkit/tasks/__init__.py` (the order is the run order).
3. Add a config key in `dotkit/config.py` if it needs one, and document it in
   `config.yaml`.
4. Add a row to [FEATURES.md](FEATURES.md). A test fails until you do.
5. Run the tests (see the README).
