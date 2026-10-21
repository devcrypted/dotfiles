# dotfiles

One YAML file describes a machine. `./install.sh` makes the machine match it, and it
is safe to rerun at any time: it changes only what differs from the config.

- What it manages, task by task: **[FEATURES.md](FEATURES.md)**
- Where to make a change (new tool, new config file, new machine): **[MANAGING.md](MANAGING.md)**

## Linux / WSL (Debian 12+, Ubuntu 24.04+, Mint, …)

```bash
git clone https://github.com/devcrypted/dotfiles.git ~/dotfiles
cd ~/dotfiles
$EDITOR config.yaml        # shells, packages, tools, apps, aliases, …
./install.sh plan          # asks about this machine on the first run, then previews
./install.sh               # apply
```

The first run checks the hardware and asks a few questions: desktop or server, NVIDIA
driver and CUDA (only if there's an NVIDIA GPU), Docker, and heavy apps. The answers
are saved in `profile.yaml` (gitignored) and pick which `apps` this machine gets: a
server gets CLI tools only. For an unattended install, answer with flags:

```bash
./install.sh --role server --no-docker --no-heavy    # or -y for the detected defaults
```

Run it as your normal user, not with `sudo`. It asks for your password when it
needs root, and a run with nothing to change never asks.

| Command | Effect |
| --- | --- |
| `./install.sh` | Apply everything, including pending one-time tasks |
| `./install.sh plan` | Show every change it would make |
| `./install.sh status` | One line per task: ok, pending, or done (one-time) |
| `./install.sh setup` | Answer the machine profile questions again |
| `./install.sh --role server --no-docker` | Set profile answers without asking (saved) |
| `./install.sh --no-once` | Routine sync: skip one-time tasks |
| `./install.sh --once-only` | Only the one-time tasks |
| `./install.sh --rerun nvidia,upgrade` | Run one-time tasks again |
| `./install.sh --only links,mise` / `--skip docker` | Pick tasks |
| `./install.sh cloud` | Set up a Claude Code cloud environment (see below) |
| `./install.sh adopt ~/.config/<tool>` | Move a tool's config into the repo and link it back |
| `./install.sh -v` | Print each command and its output |

### Making it yours

Fork, edit `config.yaml` (every key is commented) and rerun. Put per-machine
overrides in `config.local.yaml` (gitignored). The full workflow for adding tools and
config files is in [MANAGING.md](MANAGING.md).

## Claude Code cloud environments

`./install.sh cloud` sets up a [Claude Code cloud](https://code.claude.com/docs/en/cloud-environments)
VM. It links `config.local.yaml` to [`cloud.yaml`](cloud.yaml) and applies, so the VM gets
bash, your git identity and aliases, and kubectl, kind, helm and terraform from mise.
It skips what the VM already has or Claude doesn't use: Docker, node, python, the
full upgrade, other shells, the prompt and the `git` module, whose credential helper
would replace the cloud's GitHub proxy. It takes about a minute.

In claude.ai/code, open the environment selector, choose **New environment**, and set:

- **Network access**: **Custom**, with **Also include default list of common package
  managers** ticked, plus `mise.jdx.dev`, `mise-versions.jdx.dev` and `get.helm.sh`.
- **Environment variables**: `CLAUDE_ENV_FILE` puts the mise tools on PATH for every
  command. Claude's Bash tool doesn't keep PATH changes from `~/.bashrc`.

  ```text
  CLAUDE_ENV_FILE=/root/.config/shell/claude-env.sh
  BASH_DEFAULT_TIMEOUT_MS=600000
  BASH_MAX_TIMEOUT_MS=600000
  ```

- **Setup script**:

  ```bash
  #!/bin/bash
  exec > >(tee -a ~/dotfiles-setup.log) 2>&1
  git clone --depth 1 https://github.com/devcrypted/dotfiles.git ~/dotfiles
  timeout 270 ~/dotfiles/install.sh cloud || echo "dotfiles: setup failed (log above)"
  exit 0
  ```

The script must exit 0, and it has to finish in about five minutes or the VM isn't cached.
It runs again only when you edit the script or the network settings, or after about
seven days. Pushing to this repo doesn't trigger a rerun, so to pick up changes, edit a
line of the script. Edit `cloud.yaml` to change what the VM gets.

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
