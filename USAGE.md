# Usage

Everything beyond the quick start in the [README](README.md).

## Linux / WSL

`curl -fsSL https://dot.kamal.sh | bash` clones the repo to `~/dotfiles` and applies it.
To preview first, or to pass flags, clone yourself or pass them through:

```bash
git clone https://github.com/devcrypted/dotfiles.git ~/dotfiles && cd ~/dotfiles
./install.sh plan                                   # preview, then ./install.sh
curl -fsSL https://dot.kamal.sh | bash -s -- plan   # same, straight from the URL
```

The first run checks the hardware and asks a few questions: desktop or server, NVIDIA
driver and CUDA (only if there's an NVIDIA GPU), Docker, heavy apps, and on Linux Mint
how hard to debloat and harden it. The answers are saved in `profile.yaml` (gitignored)
and pick which `apps` this machine gets: a server gets CLI tools only. For an
unattended install, answer with flags:

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
| `./install.sh cloud` | Set up a Claude Code cloud VM ([CLOUD.md](CLOUD.md)) |
| `./install.sh adopt ~/.config/<tool>` | Move a tool's config into the repo and link it back |
| `./install.sh -v` | Print each command and its output |

## Making it yours

Fork, edit `config.yaml` (every key is commented) and rerun. Put per-machine
overrides in `config.local.yaml` (gitignored). The full workflow for adding tools and
config files is in [MANAGING.md](MANAGING.md).

## Linux Mint (Cinnamon)

On a desktop running Linux Mint with Cinnamon, the `cinnamon` task also brings over
the desktop itself: panel layout and applets, themes, icons, cursor, shortcuts,
gestures and Nemo settings (see `cinnamon:` in `config.yaml`). Other distros and
desktops, and servers, skip it. After changing the desktop through System Settings:

```bash
scripts/mint/cinnamon-capture.sh   # saves it into desktop/cinnamon/; review with git diff
```

On Mint, `./install.sh` also debloats and hardens the machine (the `harden` task) at
the level its profile chose: `standard`, `aggressive` or `none`. It removes
preinstalled apps you don't use (never anything that would take Mint or Cinnamon with
it), purges crash reporters, turns on the firewall, applies kernel and network sysctl
hardening, hardens sshd, and cleans caches, old configs and logs. `./install.sh plan`
lists every change first; take a Timeshift snapshot before the first run. Change the
level with `./install.sh setup`, or skip sections everywhere with `harden.skip` in
`config.yaml`. The script also works on its own: `scripts/mint/harden.sh --help`.

## Claude Code cloud environments

`./install.sh cloud` sets up a Claude Code cloud VM from [`cloud.yaml`](cloud.yaml).
**[CLOUD.md](CLOUD.md)** walks through each field of the environment dialog: network
access, network secrets, environment variables and the two-line setup script.

## Windows

`windows/install.ps1` installs the apps in [`windows/packages.json`](windows/packages.json),
sets up WSL with Ubuntu 24.04, and debloats and hardens Windows with
[`windows/harden.ps1`](windows/harden.ps1).

The first run asks whether to debloat and harden, and whether to keep OneDrive, keep
Xbox and move the taskbar left. The answers are saved in
`%ProgramData%\dotfiles\profile.json`, so reruns don't ask (`-Setup` asks again).
Hardening covers preinstalled apps and ads, telemetry, Copilot and Recall, Start menu,
taskbar, Explorer, Edge, OneDrive, Xbox, and Defender and network security. It runs
once, then again only when `harden.ps1` or your answers change (`-RerunHarden` forces it).
Run it as the user whose desktop you want changed: per-user settings go to the account
that runs it. `-SkipApps`, `-SkipWsl` and `-SkipHarden` leave a part out. Then open
Ubuntu and follow the Linux steps above.

`harden.ps1` also works on its own from a clone:

```powershell
.\windows\harden.ps1 -DryRun                    # list every change; changes nothing
.\windows\harden.ps1 -Restore <undo file>       # put back the settings it changed
```

`Get-Help .\windows\harden.ps1 -Full` lists every section.
