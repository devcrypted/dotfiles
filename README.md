# dotfiles

One YAML file describes a machine. `./install.sh` makes the machine match it, and it
is safe to rerun at any time: it changes only what differs from the config.

- What it manages, task by task: **[FEATURES.md](FEATURES.md)**
- Where to make a change (new tool, new config file, new machine): **[MANAGING.md](MANAGING.md)**

## Linux / WSL (Debian 12+, Ubuntu 24.04+, Mint, …)

```bash
git clone https://github.com/devcrypted/dotfiles.git ~/dotfiles
cd ~/dotfiles
$EDITOR config.yaml        # shells, packages, tools, aliases, …
./install.sh plan          # preview: nothing is changed
./install.sh               # apply
```

Run it as your normal user, not with `sudo`. It asks for your password when it
needs root, and a run with nothing to change never asks.

| Command | Effect |
| --- | --- |
| `./install.sh` | Apply everything, including pending one-time tasks |
| `./install.sh plan` | Show every change it would make |
| `./install.sh status` | One line per task: ok, pending, or done (one-time) |
| `./install.sh --no-once` | Routine sync: skip one-time tasks |
| `./install.sh --once-only` | Only the one-time tasks |
| `./install.sh --rerun nvidia,upgrade` | Run one-time tasks again |
| `./install.sh --only links,mise` / `--skip docker` | Pick tasks |
| `./install.sh adopt ~/.config/<tool>` | Move a tool's config into the repo and link it back |
| `./install.sh -v` | Print each command and its output |

### Making it yours

Fork, edit `config.yaml` (every key is commented) and rerun. Put per-machine
overrides in `config.local.yaml` (gitignored). The full workflow for adding tools and
config files is in [MANAGING.md](MANAGING.md).

## Windows

From an elevated PowerShell, this installs the apps in
[`windows/packages.json`](windows/packages.json) and sets up WSL with Ubuntu 24.04:

```powershell
irm https://raw.githubusercontent.com/devcrypted/dotfiles/main/windows/install.ps1 | iex
```

From a clone, `.\windows\install.ps1 -SkipWsl` or `-SkipApps` runs only one half.
Then open Ubuntu and follow the Linux steps above.

## Development

```bash
python3 -m pytest                                        # unit tests (pytest + PyYAML)
ruff check . && ruff format --check .
docker build -f tests/e2e/Dockerfile -t dotfiles-e2e . && docker run --rm dotfiles-e2e
```

The end-to-end test installs into a fresh container, checks that a second run makes
zero changes, then edits the config and checks that only those changes are applied.
CI runs it on Ubuntu 24.04 and Debian 12.
