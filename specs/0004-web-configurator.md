# 0004: Web configurator at the short install URL

Status: done

## Why

`dot.kamal.sh` only serves the install scripts. A visitor can't see what the dotfiles
install or choose anything without reading `config.yaml` and the flag list. The installer
already takes every profile answer as a flag, so a page that builds the command is cheap
and useful. Two things are missing: a way to switch off one app, and a description per app.

## Decisions

- Scope: profile answers plus per-app on/off (not every setting).
- Output: a readable command with flags; the Worker stays stateless and stores nothing.
- Windows: personas only, using the existing `-Persona` parameter.
- Audience: anyone installing these dotfiles; git name and email are never asked on the page.
- Look: dark first, clean, distinctive type and colour, equally good on phone and desktop.

## Behaviour

- `--skip-apps NAME,..` (`none` clears) on every command; saved to `profile.yaml` as
  `profile.skip_apps`. Names must exist in `apps`. Not a first-run question and not
  reported as a missing answer for older profiles. Default: skip nothing.
- `apps.<name>.about`: one line shown on the page; optional.
- `./install.sh catalog` prints the page's data as JSON (Linux personas and apps, the
  Windows personas, hardening levels). Read-only. Committed as `web/public/catalog.json`.
- `web/public/` holds a static page with no build step and no external requests.
  Linux tab: role, personas, Docker, GPU, heavy apps, hardening, per-app checkboxes
  (only apps that apply to the choices). Windows tab: personas. Both print a command
  with a copy button; a preview toggle adds `plan`.
- Worker: script routes and User-Agent detection unchanged; a browser on `/` gets the page.
- Switch off: skip nothing (default), or do not deploy the page.

## Acceptance

- [x] `skip_apps` drops an app and its apt, apt repo and mise contributions.
- [x] An unknown name in `skip_apps` is a config error listing the valid apps.
- [x] `--skip-apps` is saved, reloaded, and `none` clears it.
- [x] An old profile without `skip_apps` is not asked a question.
- [x] Every app in `config.yaml` has `about`.
- [x] `catalog` output is valid JSON and equals the committed `web/public/catalog.json`.
- [x] `buildCommand` output for sample choices matches the flags the installer accepts.
- [x] Only catalogue names reach the command; there is no free-text input.
- [x] `curl` and PowerShell User-Agents still receive the scripts from `/`.

## Out of scope

Editing aliases, shells, modules, base packages or tools; storing or sharing
configurations; per-app choice on Windows; accounts.

## Docs to update

`FEATURES.md` (machine profile table), `USAGE.md`, `web/README.md`, `README.md`.
