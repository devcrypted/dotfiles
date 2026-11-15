# AGENTS.md

Instructions for AI agents (Claude Code, opencode, Cline, …) working in this repo.
`CLAUDE.md` imports this file; edit here only.

Dotfiles for Debian/Ubuntu machines (Mint, Ubuntu, Debian, WSL) plus a Windows installer.
`./install.sh` bootstraps Python and runs `dotkit/`, which makes the machine match
`config.yaml`. Every run is idempotent: it plans, applies only what differs, and a second
run changes nothing.

## Rules (in priority order)

1. **Public repo: no personal data, no secrets.** Never write a name, email, phone,
   hostname, public IP, account/tenant ID, token, key or password into any tracked file,
   commit message or test. Personal values are asked by the installer and live only in
   gitignored `profile.yaml` / `config.local.yaml` (Windows: `%ProgramData%\dotfiles\`).
   Use `example.com` and `Ada Lovelace` style placeholders in tests and docs. Don't read
   or print `profile.yaml` or `config.local.yaml`. Never bypass the commit checks
   (`--no-verify`); fix the finding or allowlist a real false positive in `.gitleaks.toml`.
2. **Spec first.** For anything beyond a data edit (rule 5 lists those), use the `spec`
   skill: ask the owner multiple-choice questions, write `specs/NNNN-<slug>.md`, get it
   approved, then build. No code before approval.
3. **Test first (TDD).** Write the failing test in `tests/`, run it and see it fail,
   then write the code that passes it. Every behaviour change has a test. Never weaken
   or delete a test to get green.
4. **Data apart from logic; each fact once (DRY).** What to install or configure is data
   in the single `config.yaml`. `dotkit/` holds logic only: no package names, URLs or
   versions for user software in Python. Before adding a helper, search for one
   (`rg -n "def " dotkit/`). Docs link to the one place a fact lives instead of repeating it.
5. **Data edits need no spec:** adding or changing an app, tool, package, persona, alias,
   module or config file. Add software with the `add-app` skill.
6. **Nothing is forced on a machine.** Every behaviour must be switchable per machine in
   the profile or `config.local.yaml`.

## Layout

| Path | What |
| --- | --- |
| `config.yaml` | All data: packages, tools, personas, apps, aliases, settings. Every key is commented there. |
| `profile.yaml`, `config.local.yaml` | Gitignored, per machine: onboarding answers and git identity; overrides merged last. |
| `cloud.yaml` | Overrides for Claude Code cloud VMs (`./install.sh cloud`; see `CLOUD.md`). |
| `dotkit/config.py` | Typed schema, validation, `resolve()` (applies profile and personas). |
| `dotkit/onboard.py` | First-run questions; writes `profile.yaml`. |
| `dotkit/cli.py` | Commands: `apply`, `plan`, `status`, `upgrade`, `reinstall`, `setup`, `cloud`, `adopt`. |
| `dotkit/tasks/` | One file per task; run order in `tasks/__init__.py`. `plan()` must not change anything. |
| `home/<module>/` | Config files symlinked into `$HOME`. |
| `desktop/cinnamon/`, `scripts/mint/` | Mint desktop look and hardening. Never commit location or device IDs from dconf. `harden.sh` preview lines start with `~`; keep that. |
| `windows/` | `install.ps1` (winget apps: `packages.json` is the base, `personas.json` the toolsets; WSL; `harden.ps1`). Persona names match `config.yaml`, plus Windows-only `devops` (tests enforce it). |
| `web/` | Cloudflare Worker for the short install URL. `install.sh` must work piped (`curl \| bash`): everything stays inside `main()`. |
| `specs/` | One spec per feature (`specs/README.md` has the template). |
| `.claude/skills/` | `spec` (spec-driven workflow), `add-app` (package source order and checks). |

Docs: `README.md` (quick start only, keep minimal), `USAGE.md` (commands, personas),
`FEATURES.md` (one row per task; a test checks it), `MANAGING.md` (where each change
goes), `CLOUD.md`.

## Where a change goes

- **Install software:** `config.yaml` only. Source order: `apt` → `apt_repo` → `deb` →
  `mise` → `script` → `flatpak` (last resort). Details and checks: the `add-app` skill.
  Every machine: `packages` (apt) or `tools` (mise). One kind of work: a `personas` entry.
  Some machines: `apps` with `when`. GUI apps always `when: [desktop]`.
- **New profile question:** field in `Profile` (`dotkit/config.py`), `resolve()`, the
  question in `dotkit/onboard.py`, a flag in `dotkit/cli.py`, the table in
  `FEATURES.md#machine-profile`.
- **New task:** `MANAGING.md#adding-a-task`, plus its `FEATURES.md` row.
- Apps the owner doesn't want: kitty (Ghostty is the terminal).

## Checks (all must pass before a commit)

```bash
python3 -m pytest -q                   # needs pytest + PyYAML
ruff check . && ruff format --check .
pre-commit run --all-files             # everything CI runs, incl. secrets/PII scans and,
                                       # with pwsh installed, PSScriptAnalyzer and Pester
```

## Working cheaply

- Search (`rg -n`, a path or glob) before reading; read only the lines needed. Skip
  `desktop/cinnamon/spices/` and `windows/harden.ps1` unless the task is about them.
- Run one test file while iterating (`python3 -m pytest -q tests/test_x.py`), the full
  suite once at the end. Pipe long output through `tail`.
- Keep replies short: what changed, what was checked, what's left.
