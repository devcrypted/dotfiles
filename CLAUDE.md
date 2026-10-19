# CLAUDE.md

Dotfiles for Debian/Ubuntu machines (Mint, Ubuntu, Debian, WSL). `./install.sh` bootstraps
Python and runs `dotkit/`, which makes the machine match `config.yaml`. Every run is
idempotent: it plans the changes, applies only what differs, and a second run changes nothing.

## Layout

- `config.yaml`: what to install and configure (every key is commented there).
- `profile.yaml` (gitignored, one per machine): onboarding answers (`role: desktop|server`,
  `gpu`, `docker`, `heavy`). Written on the first run by `dotkit/onboard.py`.
  `./install.sh setup` asks again.
- `config.local.yaml` (gitignored): per-machine overrides, merged last.
- `dotkit/config.py`: typed config schema and `resolve()`, which applies the profile.
  It keeps only the `apps` whose `when` holds and folds their apt, apt_repo and mise
  parts into `packages`, `apt_repos` and `tools`.
- `dotkit/tasks/`: one file per task, registered in run order in `tasks/__init__.py`.
- `home/<module>/`: config files symlinked into `$HOME`.
- Docs: `README.md` (usage), `FEATURES.md` (one row per task, checked by a test),
  `MANAGING.md` (where each kind of change goes).

## Adding an application

When asked to add an app, add an entry under `apps:` in `config.yaml`. Don't write a
new task. Full reference: `MANAGING.md#adding-an-application`.

1. **Decide who gets it with `when`** (all listed conditions must hold):
   - Any GUI app: `when: [desktop]`. Servers must never get GUI apps.
   - Big downloads or RAM-hungry apps: add `heavy`.
   - Needs Docker: `docker`. Needs an NVIDIA GPU: `gpu`.
   - A CLI tool every machine needs goes in `tools:` (mise) or `packages:` (apt), not `apps`.
2. **Pick the source** in this order of preference, and check that it exists first:
   - `apt: [pkg]`: in the distro archive on Ubuntu 24.04 *and* Debian 12
     (packages.ubuntu.com / packages.debian.org).
   - `apt_repo: {key, url, suite, components, packages}`: the vendor's own apt repo.
     Use the vendor's documented key and repo URLs. `{codename}`, `{distro}`, `{arch}`
     and `{version}` are filled in.
   - `flatpak: <id>`: the Flathub id. Check that
     `https://flathub.org/api/v2/appstream/<id>` returns 200.
   - `deb: {package, url: {amd64: ..., arm64: ...}}`: a stable "latest" download URL
     (follow the redirect to confirm it serves a .deb). `package` is the dpkg name.
   - `script: {command, url}`: last resort, for an official or well-known installer
     only. Read the script before adding it.
   - `mise: {tool: version}`: a mise registry tool that only some machines need.
3. Put a short trailing comment on the entry when its name doesn't say what it is.
4. Verify: `python3 -m pytest` (the `test_full_example_*` tests load `config.yaml`), then
   `./install.sh plan` on a machine if one is available.

Apps the owner doesn't want: kitty (Ghostty is the terminal of choice).

## Other changes

- New profile question: add a field to `Profile` in `dotkit/config.py`, a condition to
  `Condition` and `resolve()`, and the question in `dotkit/onboard.py`. Then update the
  table in `FEATURES.md#machine-profile`.
- New task: follow `MANAGING.md#adding-a-task`. `plan()` must not change anything.
  Add a `FEATURES.md` row (a test enforces it).

## Checks

```bash
python3 -m pytest                      # unit tests (needs pytest + PyYAML)
ruff check . && ruff format --check .
pre-commit run --all-files             # everything CI runs, incl. secrets/PII scans
```

Never commit personal data or secrets. The gitleaks rules in `.gitleaks.toml` reject
emails other than the owner's, public IPs, UUIDs and tokens.
