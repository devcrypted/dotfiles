// Cloudflare Worker behind https://dot.kamal.sh: one short URL for both installers.
//
//   curl -fsSL https://dot.kamal.sh | bash        Linux / WSL  -> install.sh
//   irm https://dot.kamal.sh | iex                Windows      -> windows/install.ps1
//
// The same URL serves the right script by User-Agent (PowerShell's contains
// "PowerShell/"); a browser is sent to the GitHub repo. /linux and /windows pick a
// script explicitly. Deploy: cd web && wrangler deploy (see web/README.md).

const REPO = "https://github.com/devcrypted/dotfiles";
const RAW = "https://raw.githubusercontent.com/devcrypted/dotfiles/main";
const SCRIPTS = {
  linux: "/install.sh",
  windows: "/windows/install.ps1",
};

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.protocol === "http:") {
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }
    const ua = request.headers.get("user-agent") || "";
    const path = url.pathname.replace(/\/+$/, "").toLowerCase();

    let script;
    if (path === "/linux" || path === "/sh") script = SCRIPTS.linux;
    else if (path === "/windows" || path === "/win" || path === "/ps1") script = SCRIPTS.windows;
    else if (path === "") {
      if (/PowerShell\//i.test(ua)) script = SCRIPTS.windows;
      else if (/^(curl|wget|fetch)\b/i.test(ua) || /\bWget\//.test(ua)) script = SCRIPTS.linux;
      else return Response.redirect(REPO, 302);
    } else {
      return Response.redirect(REPO, 302);
    }

    const upstream = await fetch(RAW + script, { cf: { cacheTtl: 300, cacheEverything: true } });
    if (!upstream.ok) {
      return new Response(`echo "dot.kamal.sh: could not fetch ${script} (${upstream.status})" >&2; exit 1\n`, {
        status: 502,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    return new Response(upstream.body, {
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "cache-control": "public, max-age=300",
        "x-content-type-options": "nosniff",
      },
    });
  },
};
