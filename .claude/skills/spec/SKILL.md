---
name: spec
description: Spec-driven development for this dotfiles repo. Use before building any new feature, task, command, profile question or behaviour change in dotkit/, install.sh or the Windows scripts (not for data edits such as adding an app, tool, persona or alias). Asks the owner multiple-choice questions, writes the spec in specs/, and only then builds it test-first.
---

# Spec, then tests, then code

1. **Read first.** Find the code and config the request touches (`rg -n`), so the
   questions are about real choices, not things the repo already answers.
2. **Ask.** Put the open decisions to the owner as multiple-choice questions (the
   AskUserQuestion tool where available; otherwise a numbered list with lettered
   options). At most four per round, your recommendation first and marked. Ask only what
   changes the design: scope, defaults, which machines get it, how it is switched off,
   names of commands, flags and config keys. Repeat until nothing is open.
3. **Write the spec** as `specs/NNNN-<slug>.md` (next free number) from the template in
   `specs/README.md`. Keep it under a page. It contains no personal data.
4. **Get approval.** Show the spec and wait for a yes. Don't write code before it.
5. **Build test-first.** For each acceptance criterion: write the failing test, run it
   and see it fail, write the code, see it pass. Data goes in `config.yaml`, logic in
   `dotkit/`, each fact in one place.
6. **Finish.** Run every check in `AGENTS.md`, update the docs the spec lists, set the
   spec's status to `done`, and report what changed and what was verified.

If the request turns out to be a data edit, skip the spec and say so.
