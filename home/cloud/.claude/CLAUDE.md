# Cloud VM

This is a Claude Code cloud VM set up from github.com/devcrypted/dotfiles (`~/dotfiles`,
overrides in `cloud.yaml`, setup log `~/dotfiles-setup.log`). From mise (`mise ls`):
node (LTS), pnpm, supabase, wrangler, kubectl, kind, helm, terraform and rtk.

- Docker and Docker Compose are installed. If `docker info` fails, start the daemon
  with `dockerd >/var/log/dockerd.log 2>&1 &`. Nothing keeps running between sessions,
  so start the project's containers with `docker compose up -d`.
- No interactive logins (`wrangler login`, `supabase login`): API access comes from
  the environment's network secrets or variables.

## Keep context small

- Search before reading: `rg -n` or `fd` with a path or glob, then read only the lines
  you need. Don't read lockfiles, build output, `node_modules` or minified files.
- Cap noisy output: `docker compose logs --tail=50 <service>`, `| tail -n 40` on long
  builds and tests, quiet flags (`pnpm install --silent`).
- Put independent commands in one call, and use a subagent for wide searches.
- Keep replies short: what changed, what was checked, what's left.
