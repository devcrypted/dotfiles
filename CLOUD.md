# Claude Code cloud environments

A [Claude Code cloud session](https://code.claude.com/docs/en/claude-code-on-the-web)
runs on a fresh Anthropic VM: root on Ubuntu 24.04 (x86_64), with the session's
repository cloned and common toolchains already installed. Its *environment* decides
what that VM can reach and what runs before Claude starts. This page fills in each
field of the environment dialog so every session starts with these dotfiles.

`./install.sh cloud` does the machine side. It links `config.local.yaml` to
[`cloud.yaml`](cloud.yaml) and applies, so the VM gets bash, your git identity and
aliases, and these from mise: node (LTS), pnpm, the Supabase CLI, wrangler, kubectl,
kind, helm, terraform and [rtk](#token-savings). It skips:

- What the VM already has: Docker with Compose, python and uv. The VM has node too,
  but an older one than the LTS.
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
proxy, which also never gets secrets. Local Supabase in Docker uses its own local keys.
Add a secret when Claude should call a hosted API:

| Service | Allowed websites | Key | Variable its CLI or SDK reads |
| --- | --- | --- | --- |
| Supabase (CLI, Management API) | `api.supabase.com` | A personal access token (`sbp_…`) | `SUPABASE_ACCESS_TOKEN` |
| Cloudflare (wrangler) | `api.cloudflare.com` | An API token scoped to Workers/Pages | `CLOUDFLARE_API_TOKEN` |
| Resend | `api.resend.com` | An API key (`re_…`), ideally sending-only | `RESEND_API_KEY` |

All three are **Bearer**. A CLI or SDK may refuse to run while its variable is unset,
even though the proxy adds the real key. Whether a placeholder value in that variable
works with the proxy is untested. If it doesn't, put the real key in an environment
variable instead, on a personal environment only, and add the host to the network
allowlist. Give cloud sessions keys for a staging project, not production.

The fields of the **Add secret** form:

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

For this stack:

```text
ASTRO_TELEMETRY_DISABLED=1
WRANGLER_SEND_METRICS=false
CLOUDFLARE_ACCOUNT_ID=<your account id>
```

The two telemetry hosts aren't on the allowlist, so turning telemetry off avoids blocked
requests. The account ID isn't a secret, and it saves wrangler from asking which
account to use.

Optional:

| Variable | Effect |
| --- | --- |
| `BASH_MAX_OUTPUT_LENGTH=15000` | Halves how much command output reaches Claude (default 30000 characters) |
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

## In your project repo

Hooks in a cloud session run only from the session's repository (and your
organization's managed settings), never from `~/.claude/settings.json`. Per-project
setup therefore goes in the project's `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "[ \"$CLAUDE_CODE_REMOTE\" = true ] || exit 0; export PATH=\"$HOME/.local/share/mise/shims:$PATH\"; cd \"$CLAUDE_PROJECT_DIR\" && pnpm install --frozen-lockfile --silent"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "export PATH=\"$HOME/.local/share/mise/shims:$PATH\"; command -v rtk >/dev/null || exit 0; rtk hook claude"
          }
        ]
      }
    ]
  }
}
```

- **SessionStart** runs `pnpm install` when a cloud session starts. It's skipped on your
  own machine, where `CLAUDE_CODE_REMOTE` isn't `true`.
- **PreToolUse** is the [rtk](#token-savings) hook. It runs locally too, and does nothing
  where rtk isn't installed.

To start sessions with the project's Docker images already pulled, add this to the
end of the setup script. It's untested: the project's path in the VM, and whether the
repo is already cloned when the script runs, still need checking.

```bash
(dockerd >/var/log/dockerd.log 2>&1 &) && sleep 5
docker compose -f /path/to/project/docker-compose.yml pull || true
```

Keep the 5-minute budget in mind: the full Supabase stack is several gigabytes.

## Token savings

Three things keep sessions cheap:

- **`~/.claude/CLAUDE.md`** on the VM ([source](home/cloud/.claude/CLAUDE.md)) asks
  Claude to search before reading, cap noisy output and keep replies short. It's loaded
  into every session, so it stays a few lines long.
- **[rtk](https://github.com/rtk-ai/rtk)** shortens the output of common commands
  (git, test runners, package managers, docker) before Claude sees it. mise installs
  it on every machine, and the PreToolUse hook above turns it on. It only affects the
  Bash tool, not Claude's own Read and Grep. When condensed output isn't enough,
  `rtk bypass <command>` shows the full output. Telemetry is off unless you run
  `rtk telemetry enable`.
- **`BASH_MAX_OUTPUT_LENGTH`**, under [Environment variables](#environment-variables),
  is a hard cap on everything else.

## Checking a new environment

Start a session in the environment and ask Claude to run:

```bash
tail -40 ~/dotfiles-setup.log; node -v; pnpm -v; supabase -v; wrangler -v; docker compose version
```

Then run `/context` and check that `/root/.claude/CLAUDE.md` is listed under memory
files. If something's missing:

| Symptom | Cause and fix |
| --- | --- |
| `dotfiles: clone failed` in the log | The GitHub proxy refused the clone. Attach the dotfiles repo to the session too |
| A `403` or `blocked` download in the log | A domain is missing from the allowlist. Add the host named in the error |
| `kubectl: command not found`, but `~/.local/share/mise/shims/kubectl` exists | `CLAUDE_ENV_FILE` isn't set, or is set to a different path |
| `dotfiles: setup failed` | Ask Claude to run `cd ~/dotfiles && ./install.sh -v` to see the failing command |
