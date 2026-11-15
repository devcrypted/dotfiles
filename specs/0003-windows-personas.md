# 0003: Windows personas, and removing unrelated scripts

Status: done

## Why

Linux machines pick what they are for (personas); every Windows machine still got all 47
apps in `windows/packages.json`. Two scripts in `scripts/` are not machine setup, and one
named a private project in a public repo.

## Decisions

- Delete `scripts/general/` and `scripts/azure/` from the repo; copies were saved
  outside it. They remain in git history (a history rewrite is a separate decision).
- Windows gets the same persona names as Linux where both exist, plus a Windows-only
  `devops` persona (Go, Ruby, Vagrant, Pulumi, Podman, Podman Desktop).
- `windows/packages.json` becomes the base; `windows/personas.json` holds the rest.
- Only winget IDs that could be confirmed are used. Doppler, Supabase and Wrangler have
  no confirmed winget package, so they are not on the Windows `node` persona.
- Nothing is uninstalled on Windows (winget import only adds).

## Behaviour

- `install.ps1 -Persona node,k8s` (or `-Persona none`) selects personas and saves the
  answer in `profile.json`; a machine without the answer is asked once, with a numbered menu.
- `install.ps1 -ListPackages` prints the resolved winget IDs and exits, before any
  Administrator check, so it is safe to run anywhere PowerShell runs.
- `skipApps` / `extraApps` in the machine's `config.json` still apply on top.
- An unknown persona name stops the run and lists the valid names.

## Acceptance

- [x] The base list and every persona parse; personas have `about` and packages.
- [x] No package is in both the base and a persona.
- [x] Personas that exist on both systems have the same names.
- [x] No persona: base only. A persona adds its packages once, however many select it.
- [x] `skipApps` and `extraApps` still apply; an unknown persona fails with the valid names.

## Out of scope

Running winget, WSL or hardening for real (needs Windows 11). Uninstalling anything.

## Docs to update

`USAGE.md`, `MANAGING.md`, `README.md`, `AGENTS.md`, the `add-app` skill.
