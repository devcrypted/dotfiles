# Claude Code cloud environments

A [Claude Code cloud session](https://code.claude.com/docs/en/claude-code-on-the-web)
runs on a fresh Anthropic VM: root on Ubuntu 24.04 (x86_64), with the session's
repository cloned and common toolchains already installed. Its *environment* decides
what that VM can reach and what runs before Claude starts. This page fills in each
field of the environment dialog so every session starts with these dotfiles.

`./install.sh cloud` does the machine side. It links `config.local.yaml` to
[`cloud.yaml`](cloud.yaml) and applies, so the VM gets bash, your git identity and
aliases, and kubectl, kind, helm and terraform from mise. It skips:

- What the VM already has: Docker, node, python and uv.
- What Claude doesn't use: other shells, the prompt, fonts and the full upgrade.
- The `git` module, whose credential helper would replace the cloud's GitHub proxy.

It takes about a minute. To change what the VM gets, edit `cloud.yaml`.

## Opening the dialog

At [claude.ai/code](https://claude.ai/code), or under **Cloud** in the desktop app, open
the environment selector. It's the first control under the message box. Choose
**New environment** to make one. To change an existing one, hover its row and click
the settings icon. In a running session, select the caret after the session title
and choose **Edit cloud environment**.

## Name

Any name works, for example `dotfiles`. Environments you create are personal to your
account.

## Network access

| Level | What sessions can reach |
| --- | --- |
| None | Nothing through the session's network |
| Trusted (default) | Package registries, GitHub, cloud SDKs ([full list](https://code.claude.com/docs/en/cloud-environments#default-allowed-domains)) |
| Custom | Only the domains you list, plus the Trusted list if you tick the box |
| Full | Any domain |

Pick **Custom** and tick **Also include default list of common package managers**.
Then add the three domains this setup needs that aren't on the Trusted list:

```text
mise.jdx.dev
mise-versions.jdx.dev
get.helm.sh
```

`mise.jdx.dev` serves mise's apt repo, `mise-versions.jdx.dev` answers "what's the
latest version", and `get.helm.sh` serves helm. If your dialog labels the levels
differently, pick the one that lets you add domains to the default list.

**Full** also works and needs no list. The trade-off is that a prompt injection,
for example from a web page Claude reads, could then send data anywhere.

These connections work at every level, without being listed:

- GitHub, through its own proxy.
- MCP connectors you enable, because their traffic goes through Anthropic.
- The hosts of your network secrets.

## Network secrets

A network secret is an API key that Anthropic's proxy adds to requests for the hosts
you list, after each request leaves the VM. Claude can call the API, but the key never
appears in the VM, its environment variables or its files. This makes a secret the
right home for any token. An environment variable is readable by everyone who uses the
environment.

**You don't need any to start.** GitHub is already authenticated through the GitHub
proxy, which also never gets secrets. Add one when Claude should call an API that
needs a key:

| Field | What to enter |
| --- | --- |
| Name | A label, for example `Terraform Cloud` |
| Secret type | **Bearer** for a key sent in a header. Other types cover basic auth, a key in the request body, AWS SigV4, GCP and JWT |
| Allowed websites | The API's hosts, for example `app.terraform.io` (`*.` matches subdomains) |
| Custom headers | Defaults to `Authorization` with prefix `Bearer`. Paste the key as the value. For a header like `X-Api-Key`, change the name and clear the prefix |

A saved secret can't be viewed or edited. To change one, delete it and add it again.
To test it, ask Claude to `curl` the API in a session: the API answers as if the key
were in the request.

Secrets don't apply to:

- The setup script: the proxy starts with Claude Code, after the script has run.
- GitHub.
- `api.anthropic.com` and the public package registries (npm, PyPI, crates.io, Go).

## Environment variables

These use `.env` format, one `KEY=value` per line. Every command Claude runs can read
them, and so can anyone who uses the environment, so keep tokens out of them (see
[Network secrets](#network-secrets)).

Needed for this setup:

```text
CLAUDE_ENV_FILE=/root/.config/shell/claude-env.sh
BASH_DEFAULT_TIMEOUT_MS=600000
BASH_MAX_TIMEOUT_MS=600000
```

| Variable | Why |
| --- | --- |
| `CLAUDE_ENV_FILE` | Runs [claude-env.sh](home/cloud/.config/shell/claude-env.sh) before every command, which puts the mise tools on PATH. Claude's Bash tool keeps aliases from `~/.bashrc` but not PATH changes |
| `BASH_DEFAULT_TIMEOUT_MS` | Lets commands run for 10 minutes by default instead of 2 (terraform, kind, builds) |
| `BASH_MAX_TIMEOUT_MS` | The longest timeout Claude may ask for |

Optional:

| Variable | Effect |
| --- | --- |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` | Turns on agent teams |
| `CLAUDE_CODE_SUBAGENT_MODEL` | Default model for subagents |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | Token count at which the conversation is summarised |
| `MAX_MCP_OUTPUT_TOKENS` | Larger MCP tool responses (default 25000) |

Don't set these:

- `GITHUB_TOKEN` or `GH_TOKEN`: the GitHub proxy handles GitHub. A token you set is
  readable by anyone who uses the environment.
- `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`: the session sets its own value, which wins.
- `OTEL_*`: Claude Code keeps these for its own telemetry and doesn't pass them to
  commands.

A running session reads changed values only after its VM restarts. Start a new
session to try a change.

## Setup script

```bash
#!/bin/bash
exec > >(tee -a ~/dotfiles-setup.log) 2>&1
git clone --depth 1 https://github.com/devcrypted/dotfiles.git ~/dotfiles
timeout 270 ~/dotfiles/install.sh cloud || echo "dotfiles: setup failed (log above)"
exit 0
```

The script runs as root before Claude Code starts, and has two rules:

- **Exit 0.** Otherwise the session doesn't start, which is why the script ends with
  `exit 0`.
- **Finish in about five minutes.** The VM's files are then saved, and later sessions
  start from that snapshot without running the script. `timeout 270` keeps a slow
  install inside that budget.

The snapshot keeps files, not running processes. Ask Claude to start services
(`docker compose up`, a kind cluster) in each session.

The script runs again when you edit it or the network settings, and when the snapshot
expires after about seven days. **Pushing to this repo doesn't trigger a rerun.** To
pick up changes right away, edit a line of the script, for example a comment.

To add a package for every session, put it in `cloud.yaml` (`packages:` or `tools:`),
not in the script. That keeps the script at two commands.

## Checking a new environment

Start a session in the environment and ask Claude to run:

```bash
tail -40 ~/dotfiles-setup.log; kubectl version --client; git config --global user.email
```

Then run `/context` and check that `/root/.claude/CLAUDE.md` is listed under memory
files. If something's missing:

| Symptom | Cause and fix |
| --- | --- |
| `dotfiles: clone failed` in the log | The GitHub proxy refused the clone. Attach the dotfiles repo to the session too |
| A `403` or `blocked` download in the log | A domain is missing from the allowlist. Add the host named in the error |
| `kubectl: command not found`, but `~/.local/share/mise/shims/kubectl` exists | `CLAUDE_ENV_FILE` isn't set, or is set to a different path |
| `dotfiles: setup failed` | Ask Claude to run `cd ~/dotfiles && ./install.sh -v` to see the failing command |
