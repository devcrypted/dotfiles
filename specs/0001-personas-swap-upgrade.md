# 0001: Personas, swap, upgrade and a PII-free public config

Status: done (decisions marked *assumed* were made without asking; change any of them)

## Why

Every machine got the same tools whatever it was for, a dev server could not be set up
in one command, nothing updated what was installed, small VMs had no swap, and the
public `config.yaml` held the owner's name and email.

## Decisions

- Personas are data in `config.yaml`, selected per machine, and combine. They sit beside
  `role` (desktop | server), which stays. *assumed*
- Persona set: `node`, `python`, `k8s`, `ai`, `azure`; the base keeps only shell and
  terminal tools. *assumed*
- Source order: apt, vendor apt repo, vendor .deb, mise, vendor script, flatpak last.
  Vendor script ranks above flatpak because the owner asked for flatpak as the last
  resort. *assumed*
- Git identity is asked on the first run and saved in `profile.yaml`; the default is
  what git already uses on the machine.
- Swap is on by default and only acts when a machine has no swap at all.

## Behaviour

- `personas:` in `config.yaml`: `about`, `docker`, `packages`, `tools`, `apps`,
  `modules`, `aliases`. Apps gated by personas list `persona` in `when`.
- Profile answer `personas` (question, `--persona a,b`, `--persona none`). A persona
  with `docker: true` installs Docker; `docker.enabled: false` still vetoes it.
- `./install.sh upgrade`: fast-forward the clone, apply, then `apt full-upgrade`,
  `mise upgrade`, `flatpak update`, and refetch .debs no apt repo tracks.
- `./install.sh reinstall NAME…`: apps, mise tools or apt packages in this machine's config.
- `swap: {enabled, size}`; skipped in containers, on WSL, on btrfs and when the disk is
  too full. Off per machine in `config.local.yaml`.
- `script.apt`: use the distro package instead of the script where the archive has it.
- `user:` is absent from `config.yaml`; onboarding writes it to `profile.yaml`.

## Acceptance

- [x] No persona: base only. A persona adds its parts; personas share apps and tools.
- [x] Conflicting tool versions, unknown personas, apps or modules fail validation.
- [x] `--role server --persona node -y` plans Node, pnpm, Wrangler, Supabase, Doppler,
      Claude Code and Docker, and no Kubernetes tools.
- [x] `upgrade` reruns the apt upgrade and each task's upgrade step; `plan` never does.
- [x] Swap is planned only when none exists; an existing swap file is enabled, not remade.
- [x] The public config loads with an empty identity.

## Out of scope

Personas for the Windows installer. Uninstalling apt packages, flatpaks or .debs when
an app or persona is removed (only mise tools are removed, as before).

## Docs to update

`README.md`, `USAGE.md`, `FEATURES.md`, `MANAGING.md`, `CLOUD.md`, `AGENTS.md`.
