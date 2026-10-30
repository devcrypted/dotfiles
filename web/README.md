# dot.kamal.sh

A Cloudflare Worker that gives the installers a short URL:

```bash
curl -fsSL https://dot.kamal.sh | bash      # Linux / WSL: install.sh (clones to ~/dotfiles)
```

```powershell
irm https://dot.kamal.sh | iex              # Windows: windows/install.ps1
```

The same URL serves `install.sh` to curl/wget and `windows/install.ps1` to PowerShell
(by User-Agent), and sends browsers to the GitHub repo. `/linux` and `/windows` pick
a script explicitly. Scripts come from the `main` branch on GitHub, cached for 5
minutes, so a push is live within that time; nothing here needs redeploying.

## Deploy

`kamal.sh` is on Cloudflare, so the Worker can own the `dot` subdomain:

```bash
cd web
wrangler login      # once
wrangler deploy     # creates dot.kamal.sh (DNS record + certificate) and the Worker
curl -fsSL https://dot.kamal.sh | head -3   # should print the top of install.sh
```

Redeploy only after editing `worker.js` or `wrangler.toml`. To use another hostname,
change `routes` in `wrangler.toml` and the URLs in README.md, USAGE.md, `install.sh`
and `windows/install.ps1`.
