import assert from "node:assert/strict";
import test from "node:test";
import worker from "./worker.js";

const asset = new Response("<html>page</html>", { headers: { "content-type": "text/html" } });
const env = { ASSETS: { fetch: async (req) => (new URL(req.url).pathname === "/nope.txt" ? new Response("", { status: 404 }) : asset.clone()) } };
globalThis.fetch = async (url) => new Response(`SCRIPT ${url}`);
const get = (path, ua) => worker.fetch(new Request(`https://dot.kamal.sh${path}`, { headers: ua ? { "user-agent": ua } : {} }), env);

test("curl and wget get install.sh from /", async () => {
  for (const ua of ["curl/8.5.0", "Wget/1.21"]) assert.match(await (await get("/", ua)).text(), /SCRIPT .*\/install\.sh$/);
});

test("PowerShell gets install.ps1 from / and /windows", async () => {
  assert.match(await (await get("/", "Mozilla/5.0 WindowsPowerShell/5.1")).text(), /install\.ps1$/);
  assert.match(await (await get("/windows", "curl/8")).text(), /install\.ps1$/);
});

test("a browser gets the page with a strict CSP", async () => {
  const res = await get("/", "Mozilla/5.0 Firefox/130.0");
  assert.equal(await res.text(), "<html>page</html>");
  assert.match(res.headers.get("content-security-policy"), /default-src 'none'/);
  assert.equal(res.headers.get("x-content-type-options"), "nosniff");
});

test("unknown paths go to the repo", async () => {
  const res = await get("/nope.txt", "Mozilla/5.0");
  assert.equal(res.status, 302);
  assert.match(res.headers.get("location"), /github\.com/);
});
