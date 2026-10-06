# Features

`./install.sh` runs these tasks top to bottom. Each one checks the system first and
changes only what differs from `config.yaml`, so reruns are cheap and safe.
**One-time** tasks are recorded after they succeed and are skipped on later runs.
They run again when their config section changes or with `--rerun <task>`.

| Task | Kind | What it does |
| --- | --- | --- |
| `upgrade` | one-time | `apt full-upgrade` on a fresh machine (`upgrade: true`). |
| `packages` | always | Installs `packages` plus what other enabled tasks need (shells, zsh plugins, …) in one apt run. Never uninstalls. |
| `repos` | always | Adds each `apt_repos` entry with its own signed-by keyring and installs its packages. Repos removed from config are removed (packages stay). |
| `links` | always | Symlinks every file in `home/<module>/` to the same path in `$HOME`. Whatever was there is moved to `~/.local/state/dotfiles/backups/<run>/` with the same folder structure. Links for removed files or disabled modules are pruned, as are old GNU Stow links into the repo. |
| `shellenv` | always | Renders `aliases`, `env`, `path` and `mask` into `~/.config/dotfiles/` for bash/zsh (`alias`) and fish (`abbr`). |
| `shells` | always | Installs `shells.install`, adds a small managed block to `~/.bashrc` / `~/.zshrc` that loads `home/<shell>/`, and sets the login shell to `shells.default`. Fish needs no block, because it loads `conf.d/` by itself. |
| `git` | always | Writes `user.name` / `user.email` to the machine-local `~/.gitconfig`. Shared settings are in `~/.config/git/config`. |
| `hooks` | always | Installs this repo's [pre-commit](https://pre-commit.com) checks (see below) so every clone checks commits. `pre_commit: false` turns it off. |
| `mise` | always | Installs [mise](https://mise.jdx.dev) and syncs global `tools` (runtimes and CLIs, matching your CPU architecture). Tools removed from config are uninstalled. |
| `fonts` | always | Installs each Nerd Font in `fonts` to `~/.local/share/fonts`. Skipped on WSL. |
| `docker` | always | Installs Docker Engine (with buildx and compose) from download.docker.com unless a `docker` CLI already exists. If the existing Docker lacks buildx, installs the matching package. Adds you to the `docker` group. |
| `nvidia` | one-time | When an NVIDIA GPU is present (and not WSL): installs the open or proprietary driver (`ubuntu-drivers` on Ubuntu/Mint, the CUDA repo on Debian), plus `nvidia-container-toolkit` registered with Docker. |
| `ssh` | one-time | Creates `~/.ssh/id_ed25519` if it doesn't exist. |
| `sudo` | always | `sudo_nopasswd: true` adds a `visudo`-validated `/etc/sudoers.d/90-dotfiles`; switching it back to `false` removes it. |

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
- **Navigation and history:** zoxide (`z`), fzf (Ctrl+R, Ctrl+T, Alt+C), typing a directory
  name to cd into it, Up/Down searching history by what you've typed, a large shared
  history, and Ctrl+Backspace to delete a word.
- **zsh extras:** autosuggestions, syntax highlighting, case-insensitive menu completion.

## Commit checks (`.pre-commit-config.yaml`)

Every `git commit` in this repo runs the following. If any check fails, the commit is refused.

- **Secrets:** [gitleaks](https://github.com/gitleaks/gitleaks) with its full default rule
  set, plus `detect-private-key`, and a list of file names that are never allowed
  (`config.local.yaml`, `.env`, `id_*`, `*.pem`/`*.key`, `hosts.yml`, `credentials`, …).
- **Personal data:** gitleaks rules in `.gitleaks.toml` for email addresses (yours and
  placeholders are allowed), public IP addresses, UUIDs (cloud tenant/subscription IDs),
  phone numbers and card numbers.
- **Blocked words:** anything in `blocked_words` (set it in `config.local.yaml`, e.g. an
  employer's or client's name) may never appear in a committed file.
- **Quality:** ruff (lint + format), shellcheck, shfmt, fish_indent, `zsh -n`,
  markdownlint, YAML/JSON/TOML validity, whitespace and line-ending fixes, large-file guard,
  and the unit tests.

`pre-commit run --all-files` runs everything by hand.

## Design notes

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
