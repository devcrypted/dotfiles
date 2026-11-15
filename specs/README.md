# Specs

One short file per feature, written and approved before any code (see `AGENTS.md`; AI
agents use the `spec` skill). Data edits (an app, tool, persona, alias) need no spec.

Name: `NNNN-<slug>.md`, numbered in order. Template:

```markdown
# NNNN: Title

Status: draft | approved | done

## Why

The problem, in two or three sentences.

## Decisions

Each question that was asked and the answer chosen (one line each).

## Behaviour

What the user sees: commands, flags, config keys with defaults, what happens on
machines it doesn't apply to, and how to switch it off per machine.

## Acceptance

- [ ] One testable statement per line. Each becomes at least one test.

## Out of scope

What this deliberately leaves alone.

## Docs to update
```

Specs never contain personal data, hostnames or secrets.
