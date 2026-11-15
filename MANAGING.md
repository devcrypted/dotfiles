# Managing your setup

The rule: **anything you want on every machine goes into this repo**. Either as a
line in `config.yaml` (what to install) or as a file under `home/` (how it's
configured). Then commit. A new machine is just `git clone` + `./install.sh`.

## Where each change goes

| I want to… | Change | Notes |
| --- | --- | --- |
| Install an application only some machines get (GUI apps, heavy tools) | `apps:` in `config.yaml` | See [Adding an application](#adding-an-application). |
| Install tools for one kind of work (a language, a cloud, a stack) | `personas:` in `config.yaml` | See [Adding a persona](#adding-a-persona). |
| Install a system package on every machine | `packages:` in `config.yaml` | The first choice: anything in the distro archive of Ubuntu 24.04 and Debian 12. Removing the line does *not* uninstall. |
| Install a CLI tool on every machine that apt lacks or ships too old | `tools:` in `config.yaml` | Check the [mise registry](https://mise.jdx.dev/registry.html). Removing the line uninstalls it. |
| Update everything | `./install.sh upgrade` | Pulls this repo, applies it, then upgrades apt packages, mise tools, flatpaks and .debs. |
| Repair a broken install | `./install.sh reinstall <name>…` | Names from `apps`, `tools`, a persona's tools, or `packages`. |
| Install from a vendor's apt repo | `apt_repos:` in `config.yaml` | Key URL, repo URL and the packages it provides. See the comment in `config.yaml`. |
| Keep a tool's config file | `./install.sh adopt ~/.config/<tool>` | Moves it into `home/<tool>/`, links it back and enables the module. |
| Edit a managed config file | Edit it in place (`~/.config/...`) | It's a symlink into the repo, so the change shows up in `git status`. |
| Add an alias, env var or PATH entry | `aliases:` / `env:` / `path:` in `config.yaml` | Applies to bash, zsh and fish. |
| Add a shell function or setting | `home/shell/.config/shell/common.sh` (bash+zsh), `home/fish/.config/fish/` (fish) | A shell-specific setting goes in `home/<shell>/`. |
| Change the login shell or prompt | `shells.default`, `prompt` in `config.yaml` | |
| Change what this machine is (desktop/server, personas, GPU, Docker, heavy apps) or its git identity | `./install.sh setup` | Rewrites `profile.yaml` (gitignored). |
| Change something on one machine only | `config.local.yaml` (gitignored) | Merged over `config.yaml`; `key: null` removes a key. |
| Add a Windows app | `windows/packages.json` (every machine) or `windows/personas.json` (one kind of work) | Then rerun `windows/install.ps1`; `-ListPackages` previews. Store-only apps go in the `msstore` source by Store ID (`9NKSQGP7F2NH` is WhatsApp). A package is in one place, never both (a test checks). |
| Keep a Cinnamon desktop change (Linux Mint) | `scripts/mint/cinnamon-capture.sh` | Saves settings into `desktop/cinnamon/`; Spices applets and themes go in `cinnamon:` in `config.yaml`. |
| Remove a preinstalled app or harden something | `scripts/mint/harden.sh`, `windows/harden.ps1` | Lists at the top of each script. `./install.sh` (the `harden` task) and `windows/install.ps1` run them again when the script changes. |
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
   of git (see [Secrets](#secrets-and-personal-data)).
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

## Secrets and personal data

This repo is public, so nothing personal or secret may be committed: no names, emails,
phone numbers, hostnames, public IPs, account or tenant IDs, tokens, keys or passwords.

- Personal values a machine needs (git name and email) are asked by the installer and
  live in `profile.yaml`. Anything else machine-specific goes in `config.local.yaml`.
  Both are gitignored and refused by the commit checks.
- If a tool mixes settings and secrets in one file, adopt only the settings file, or
  keep the secret part in an untracked file the tool can include (many support an
  `include` directive, like `~/.gitconfig` does here).
- Every commit, commit message and push is scanned by gitleaks (default secret rules
  plus the PII rules in `.gitleaks.toml`), a forbidden-files check and your
  `blocked_words`; CI repeats it over the whole history. See
  [FEATURES.md](FEATURES.md#commit-checks-pre-commit-configyaml).
- Put your own name, employer and client names in `blocked_words` in
  `config.local.yaml`: no pattern can recognise a bare name, that list can.
- On GitHub, keep **Secret scanning** and **Push protection** turned on (Settings →
  Code security). They are free for public repos and catch what a skipped hook misses.
- A secret that was pushed is compromised even after a force-push: rotate it first.

## Adding an application

Add an entry under `apps:` in `config.yaml`, then `./install.sh plan` and commit.

```yaml
apps:
  <name>:                      # a-z, 0-9 and -
    when: [desktop, heavy]     # optional; every condition must hold on the machine
    flatpak: org.example.App   # one or more sources, see below
```

**`when`** decides which machines get it, from the [machine profile](FEATURES.md#machine-profile):

| Condition | Holds when |
| --- | --- |
| `desktop` | the machine is a desktop (use for every GUI app) |
| `server` | the machine is a server |
| `heavy` | the user said yes to heavy apps (big downloads, lots of RAM or disk) |
| `docker` | Docker is installed |
| `gpu` | an NVIDIA GPU is present and the user said yes to it |
| `persona` | a persona selected on the machine lists the app under its `apps` |

No `when` means every machine.

**Sources, in order of preference.** Native packages come first: use the first source in
this table that exists for the app, and check that it exists before adding it. An app
may list several, and all of them are installed (`podman-desktop` pairs `apt: [podman]`
with its flatpak).

| # | Source | Use when | Updated by | Example |
| --- | --- | --- | --- | --- |
| 1 | `apt: [pkg, …]` | The archive of Ubuntu 24.04 *and* Debian 12 has it, in a usable version | apt | `timeshift` |
| 2 | `apt_repo: {key, url, suite, components, packages}` | The vendor runs an apt repo | apt | `brave`, `doppler`, `claude-code` |
| 3 | `deb: {package, url: {amd64: …, arm64: …}}` | The vendor offers a stable "latest .deb" URL | apt when the .deb adds its repo (`vscode`), else `./install.sh upgrade` refetches it (`bitwarden`) | `vscode` |
| 4 | `mise: {tool: version}` | A CLI in the [mise registry](https://mise.jdx.dev/registry.html) | `./install.sh upgrade` | `lazydocker` |
| 5 | `script: {command, url, apt}` | The vendor's own installer is the only native route; it runs unless `command` is on `PATH`. `apt` names the distro package to use instead on releases that have it | the app itself | `ghostty`, `zed` |
| 6 | `flatpak: <app id>` | Last resort: none of the above exists. The id is in the [Flathub](https://flathub.org) page URL | `./install.sh upgrade` | `todoist` |

CLI tools every machine gets stay in `packages:` (apt, preferred) or `tools:` (mise).
Removing an app stops it from being installed on new machines. Only its `mise` tools
are uninstalled; apt packages, flatpaks and debs stay until you remove them by hand.

## Adding a persona

A persona is data only: an entry under `personas:` in `config.yaml`, no code.

```yaml
personas:
  rust:                          # a-z, 0-9 and -
    about: Rust development (rustup toolchain, cargo tools)   # shown in the question
    docker: false                # true: selecting the persona installs Docker
    packages: [pkg-config]       # apt, first choice
    tools: {rust: latest}        # mise
    apps: [some-app]             # entries in `apps` with `persona` in their `when`
    modules: [cargo]             # home/<module>/ to link
    aliases: {c: cargo}
```

Personas combine, so a tool or app may appear in several (`node` and `ai` both list
`claude-code`), as long as each tool has one version everywhere. A machine selects
personas in its profile: `./install.sh setup` or `--persona rust,node`.

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
5. Run the tests (see [Development](#development)).

## Development

Changes follow three rules, spelled out for AI agents in [AGENTS.md](AGENTS.md):

- **Spec first.** Anything beyond a data edit starts as a short spec in `specs/`
  (template: [specs/README.md](specs/README.md)), agreed before code is written.
- **Test first.** Write the failing test, then the code that passes it.
- **Data apart from logic, each fact once.** What to install lives in `config.yaml`;
  `dotkit/` only knows how. Nothing is stated in two places.

```bash
python3 -m pytest                                        # unit tests (pytest + PyYAML)
ruff check . && ruff format --check .
docker build -f tests/e2e/Dockerfile -t dotfiles-e2e . && docker run --rm dotfiles-e2e
```

The end-to-end test installs into a fresh container, checks that a second run makes
zero changes, then edits the config and checks that only those changes are applied.
CI runs it on Ubuntu 24.04 and 26.04 and Debian 12 and 13.
