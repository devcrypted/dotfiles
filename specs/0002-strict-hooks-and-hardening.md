# 0002: Strict commit checks and public-repo hardening

Status: done

## Why

A secret could still reach GitHub through a commit message, a `--no-verify` commit or a
clone whose hooks were never installed, and CI ran a different gitleaks than the hooks.
Several defaults were unsafe or unpinned for a repo other people will run.

## Decisions

- Approved by the owner from the audit list: hook gaps, write-mode formatters, and
  flags 1 to 6 (name in a tracked file, passwordless sudo default, unpinned third-party
  installer, CI pinning and permissions, Dependabot, licence).
- Licence: MIT, held by the GitHub account name, not a personal name.
- `scripts/general/` and `scripts/azure/` stayed here at this point; spec 0003 removes them.

## Behaviour

- Three git hooks are installed: `pre-commit` (all checks, formatters rewrite files),
  `commit-msg` (secrets, PII and blocked words in the message), `pre-push` (gitleaks
  over the commits being pushed, so a skipped commit hook is caught before upload).
- A clone with only the old commit hook gets the two new ones on the next run.
- CI runs the same hooks with the same pinned gitleaks, plus the history scan.
- `sudo_nopasswd` defaults to `false`; a machine opts in via `config.local.yaml`.
- The Ghostty installer URL is pinned to a commit.
- CI actions are pinned to commits, with read-only permissions; Dependabot proposes
  updates to actions and hook versions.

## Acceptance

- [x] The hooks task plans an install until all three hook files are present.
- [x] A commit message containing a token is refused.
- [x] A push containing a commit with a token is refused.
- [x] Only the secret checks opt in to `commit-msg` and `pre-push` (a few upstream file
      checks also declare `pre-push` themselves; they are quick and harmless there).
- [x] The public config does not enable passwordless sudo.

## Out of scope

GitHub push protection and branch protection (repo settings, owner only). Checksums
for "latest" `.deb` downloads.

## Docs to update

`FEATURES.md`, `MANAGING.md`, `USAGE.md`.
