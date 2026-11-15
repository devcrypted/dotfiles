// Cloudflare Worker behind https://dot.kamal.sh: one short URL for both installers.
//
//   curl -fsSL https://dot.kamal.sh | bash        Linux / WSL  -> install.sh
//   irm https://dot.kamal.sh | iex                Windows      -> windows/install.ps1
//
// The same URL serves the right script by User-Agent (PowerShell's contains
// "PowerShell/"); a browser gets the configurator page from public/ (static assets).
// /linux and /windows pick a script explicitly. Anything else is looked up in public/,
// then sent to the GitHub repo. Deploy: cd web && wrangler deploy (see web/README.md).

const REPO = "https://github.com/devcrypted/dotfiles";
const RAW = "https://raw.githubusercontent.com/devcrypted/dotfiles/main";
const SCRIPTS = {
  linux: "/install.sh",
  windows: "/windows/install.ps1",
};

const PAGE_HEADERS = {
  "content-security-policy":
    "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  "x-content-type-options": "nosniff",
  "referrer-policy": "no-referrer",
};

async function page(request, env) {
  const asset = env.ASSETS ? await env.ASSETS.fetch(request) : null;
  if (!asset || asset.status === 404) return Response.redirect(REPO, 302);
  const response = new Response(asset.body, asset);
  for (const [name, value] of Object.entries(PAGE_HEADERS)) response.headers.set(name, value);
  return response;
}

export default {
  async fetch(request, env) {
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
      else return page(request, env);
    } else {
      return page(request, env);
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
