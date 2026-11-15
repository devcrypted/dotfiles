# dot.kamal.sh

A Cloudflare Worker that gives the installers a short URL:

```bash
curl -fsSL https://dot.kamal.sh | bash      # Linux / WSL: install.sh (clones to ~/dotfiles)
```

```powershell
irm https://dot.kamal.sh | iex              # Windows: windows/install.ps1
```

The same URL serves `install.sh` to curl/wget and `windows/install.ps1` to PowerShell
(by User-Agent), and shows browsers the configurator page. `/linux` and `/windows` pick
a script explicitly. Scripts come from the `main` branch on GitHub, cached for 5
minutes, so a push is live within that time; nothing here needs redeploying.

## Configurator page (`public/`)

A static page, no build step and no outside requests (fonts are self-hosted, see
`public/fonts/`; CSP is set in `worker.js`). A visitor picks a role, toolsets and apps
and gets a command such as
`curl -fsSL https://dot.kamal.sh | bash -s -- --role server --personas node --skip-apps jan`.
Nothing is stored or sent; names come only from `public/catalog.json`.

- `catalog.json` is generated: `./install.sh catalog > web/public/catalog.json`
  (a test fails when it is stale). Add an app or persona in `config.yaml` (with `about:`),
  regenerate, redeploy.
- `logic.js` builds the commands; `app.js` draws the page. Tests: `node --test web/public/logic.test.mjs web/worker.test.mjs`.
- Preview locally: `cd web && wrangler dev`.
- Fonts: Instrument Serif and JetBrains Mono, both SIL Open Font License 1.1, via Fontsource.

## Deploy

`kamal.sh` is on Cloudflare, so the Worker can own the `dot` subdomain:

```bash
cd web
wrangler login      # once
wrangler deploy     # creates dot.kamal.sh (DNS record + certificate) and the Worker
curl -fsSL https://dot.kamal.sh | head -3   # should print the top of install.sh
```

Redeploy after editing `worker.js`, `wrangler.toml` or anything in `public/`. To use another hostname,
change `routes` in `wrangler.toml` and the URLs in README.md, USAGE.md, `install.sh`
and `windows/install.ps1`.
