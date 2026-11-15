# Features

`./install.sh` runs these tasks top to bottom, for the machine described by
`config.yaml` plus this machine's profile (see [Machine profile](#machine-profile)). Each one checks the system first and
changes only what differs from `config.yaml`, so reruns are cheap and safe.
**One-time** tasks are recorded after they succeed and are skipped on later runs.
They run again when their config section changes or with `--rerun <task>`.

| Task | Kind | What it does |
| --- | --- | --- |
| `swap` | always | Creates a swap file at `/swapfile` (size from RAM, or `swap.size`), turns it on and adds it to `/etc/fstab`, but only on a machine with no swap at all. Skipped in containers and on WSL. `swap: {enabled: false}` turns it off. |
| `upgrade` | one-time | `apt full-upgrade` on a fresh machine (`upgrade: true`), and again on every `./install.sh upgrade`. |
| `packages` | always | Installs `packages` plus what other enabled tasks need (shells, zsh plugins, …) in one apt run. Never uninstalls. |
| `repos` | always | Adds each `apt_repos` entry with its own signed-by keyring and installs its packages. Repos removed from config are removed (packages stay). |
| `links` | always | Symlinks every file in `home/<module>/` to the same path in `$HOME`. Whatever was there is moved to `~/.local/state/dotfiles/backups/<run>/` with the same folder structure. Links for removed files or disabled modules are pruned, as are old GNU Stow links into the repo. |
| `shellenv` | always | Renders `aliases`, `env`, `path` and `mask` into `~/.config/dotfiles/` for bash/zsh (`alias`) and fish (`abbr`). |
| `shells` | always | Installs `shells.install`, adds a small managed block to `~/.bashrc` / `~/.zshrc` that loads `home/<shell>/`, and sets the login shell to `shells.default`. Fish needs no block, because it loads `conf.d/` by itself. |
| `git` | always | Writes the name and email from this machine's `profile.yaml` to the machine-local `~/.gitconfig`. Shared settings are in `~/.config/git/config`. |
| `hooks` | always | Installs this repo's [pre-commit](https://pre-commit.com) checks (see below) so every clone checks commits. `pre_commit: false` turns it off. |
| `mise` | always | Installs [mise](https://mise.jdx.dev) and syncs global `tools` (runtimes and CLIs, matching your CPU architecture). Tools removed from config are uninstalled. |
| `fonts` | always | Installs each Nerd Font in `fonts` to `~/.local/share/fonts`. Skipped on WSL and on servers. |
| `apps` | always | Installs the `apps` this machine's profile selects that come as a flatpak (Flathub, system-wide), a `.deb` download or an install script. Their `apt`, `apt_repo` and `mise` parts are installed by `packages`, `repos` and `mise`. One app failing is reported at the end and doesn't stop the run. |
| `cinnamon` | one-time | Only on a Linux Mint Cinnamon desktop whose profile said yes to the saved desktop look. Downloads the `cinnamon.applets` and `cinnamon.themes` from [Cinnamon Spices](https://cinnamon-spices.linuxmint.com), installs `cinnamon.packages`, copies the saved applet settings in `desktop/cinnamon/spices/` and loads `desktop/cinnamon/dconf.ini` (panels, themes, shortcuts, gestures, Nemo). Runs again when either changes; `scripts/mint/cinnamon-capture.sh` saves the current desktop into the repo. |
| `docker` | always | Installs Docker Engine (with buildx and compose) from download.docker.com unless a `docker` CLI already exists. If the existing Docker lacks buildx, installs the matching package. Adds you to the `docker` group. |
| `nvidia` | one-time | When the profile says yes to the GPU and an NVIDIA GPU is present (and not WSL): installs the open or proprietary driver (`ubuntu-drivers` on Ubuntu/Mint, the CUDA repo on Debian) unless a driver of that flavor is already running or installed, plus `nvidia-container-toolkit` registered with Docker when Docker is installed. |
| `cuda` | always | Same conditions, WSL included, with `nvidia.cuda: true`: installs `cuda-toolkit` from NVIDIA's repo for this release and puts `/usr/local/cuda/bin` on `PATH`. Skipped when any working `nvcc` exists, however it was installed. An interrupted install is finished from the packages already downloaded instead of starting over, and every install is checked by running `nvcc --version`. |
| `ssh` | one-time | Creates `~/.ssh/id_ed25519` if it doesn't exist. |
| `sudo` | always | Off by default. `sudo_nopasswd: true` (set it per machine in `config.local.yaml`) adds a `visudo`-validated `/etc/sudoers.d/90-dotfiles`; switching it back to `false` removes it. |
| `harden` | one-time | Linux Mint only, when the profile's `harden` answer is `standard` or `aggressive`: runs [`scripts/mint/harden.sh`](scripts/mint/harden.sh). It purges unused preinstalled apps (never one apt would take Mint or Cinnamon down with) and crash reporters, stops network discovery services, hardens sshd, turns on ufw, applies kernel/network sysctl hardening, turns off core dumps, enables automatic updates and cleans caches and logs. `harden.skip` in `config.yaml` leaves sections alone. Runs again when the answer, the skip list or the script changes. |

## Machine profile

The first `./install.sh` (or `plan`) on a machine detects its hardware (RAM, CPUs,
NVIDIA GPU, desktop session) and asks up to seven questions, then your git name and
email (defaults: what git already uses on the machine). The answers go into
`profile.yaml` (gitignored), so they're asked only once, and nothing personal is ever
in the public `config.yaml`:

| Question | Default | Effect |
| --- | --- | --- |
| Desktop or server? | desktop when a desktop session or display manager exists (not WSL) | A server gets no `when: [desktop]` apps and no fonts. |
| Personas? | none | Adds each selected persona's packages, mise tools, apps, modules and aliases ([list](USAGE.md#personas)). A persona that needs Docker installs it, so that question is skipped. |
| NVIDIA driver and CUDA? | yes; not asked without an NVIDIA GPU | `nvidia`, `cuda` and `when: [gpu]` apps. |
| Docker? | yes on a desktop with 4 GB+ RAM, no on a server | `docker` and `when: [docker]` apps. |
| Heavy apps? | yes on a desktop with 8 GB+ RAM, no on a server | `when: [heavy]` apps. |
| Debloat and harden? | `standard`; only asked on Linux Mint (elsewhere `none`) | `standard`, `aggressive` or `none` for the `harden` task. |
| Apply the saved Cinnamon desktop? | yes; only asked on a Linux Mint Cinnamon desktop (elsewhere no) | The `cinnamon` task. No leaves the desktop exactly as it is. |

`./install.sh setup` asks again with the saved answers as defaults. When a newer version of
this repo adds a question, the next run asks only that one and keeps the other answers. Flags answer
without asking and are saved too: `--role desktop|server`, `--persona node,k8s` (`none` clears), `--gpu`/`--no-gpu`,
`--docker`/`--no-docker`, `--heavy`/`--no-heavy`, `--skip-apps jan,zed` (leave those `apps` out; not a question, `none` clears), `--harden none|standard|aggressive`, `--cinnamon`/`--no-cinnamon`, and `-y` to take the detected
defaults for anything not given. Without a terminal (CI, cloud-init) the detected
defaults are used and saved. `config.yaml` can still veto: `docker.enabled: false` or
`nvidia.enabled: false` wins over a profile that says yes.

## Shell features (bash, zsh, fish)

All three shells are set up the same way, with no framework:

- **Prompt.** [Starship](https://starship.rs) by default. Set `prompt: builtin` for a
  dependency-free prompt with the path, git branch (with a dirty marker in bash/zsh) and a
  `❯` that turns red after a failed command. `user@host` only shows over SSH.
- **Aliases and env** come from `config.yaml` (`abbr` in fish).
- **Better defaults:** `ls`/`ll`/`la`/`lt` via eza and `cat` via bat when installed,
  `fd`/`bat` mapped to Debian's `fdfind`/`batcat`, and human-readable `df`/`du`/`free`.
- **Functions:** `mkcd DIR`, `up [N]`, `mask CMD…`, and `extract FILE…` for any
  common archive format.
- **Navigation and history:** zoxide (`z`), fzf (Ctrl+T, Alt+C), atuin (Ctrl+R, searchable
  history; Up/Down stay prefix search), typing a directory
  name to cd into it, Up/Down searching history by what you've typed, a large shared
  history, and Ctrl+Backspace to delete a word.
- **zsh extras:** autosuggestions, syntax highlighting, case-insensitive menu completion.

## Commit checks (`.pre-commit-config.yaml`)

Three git hooks guard this repo, so a secret has to get past all of them to reach GitHub:

| Hook | Runs | Checks |
| --- | --- | --- |
| `pre-commit` | on `git commit`, over the staged files | Everything listed below. Formatters rewrite the file, so you only re-stage. |
| `commit-msg` | on `git commit`, over the message | Secrets, personal data and blocked words. |
| `pre-push` | on `git push`, over every commit being pushed | Secrets and personal data. Catches commits made with `--no-verify` or before the hooks were installed, while they are still only on your machine. |

CI runs the same hooks with the same pinned versions, then scans the whole history.
Hooks can be skipped on a laptop, so also keep GitHub's **Secret scanning** and **Push
protection** on (Settings → Code security): that check cannot be bypassed locally.

- **Secrets:** [gitleaks](https://github.com/gitleaks/gitleaks) with its full default rule
  set, plus `detect-private-key`, and a list of file names that are never allowed
  (`config.local.yaml`, `profile.yaml`, `.env`, `id_*`, `*.pem`/`*.key`, `hosts.yml`,
  `credentials`, …).
- **Personal data:** gitleaks rules in `.gitleaks.toml` for email addresses (only
  placeholders are allowed), public IP addresses, UUIDs (cloud tenant/subscription IDs),
  home directory paths that name a real user, phone numbers and card numbers.
- **Blocked words:** anything in `blocked_words` (set it in `config.local.yaml`, e.g. an
  employer's or client's name) may never appear in a committed file.
- **Quality:** ruff (lint + format), shellcheck, shfmt, fish_indent, `zsh -n`,
  markdownlint (rumdl), YAML/JSON/TOML validity, whitespace and line-ending fixes, large-file guard,
  and the unit tests.

ruff, shfmt, fish_indent, rumdl and the whitespace fixers fix what they find and stop
the commit once; stage the result and commit again. `pre-commit run --all-files` runs
everything by hand.

## Design notes

- **Shows progress.** A slow step gets a live line under it after a second: elapsed time,
  the latest output and, where the step reports it (apt downloads and installs, file
  downloads), a percentage bar. It's drawn only on a terminal; `-v` streams the full output.
- **Runs as you, not root.** `sudo` is used only for commands that need it, and the
  password is asked at most once per run. A run with nothing to change never prompts.
- **Rc files stay machine-local.** `~/.bashrc`, `~/.zshrc`, `~/.config/fish/config.fish`
  and `~/.gitconfig` are not symlinked, so installers that append to them (nvm, gh,
  cloud CLIs, …) never change this repo.
- **Bookkeeping** lives in `~/.local/state/dotfiles/state.json`. It records which
  one-time tasks ran, which links, tools and repos the installer created, and
  nothing else.
- **Supported:** Debian 12+, Ubuntu 24.04+ and derivatives (Linux Mint, Pop!_OS, WSL Ubuntu).
  Windows setup is separate, in [`windows/`](windows/install.ps1).
