// Pure functions behind the configurator: no DOM, so `node --test web/` can run them.
// Only names found in the catalogue ever reach a command, so there is nothing to inject.

export const BASE_URL = "https://dot.kamal.sh";
const NAME = /^[a-z0-9][a-z0-9_-]*$/;

export const defaults = () => ({
  role: "desktop",
  personas: [],
  docker: true,
  gpu: true,
  heavy: true,
  harden: "none",
  skip: [],
});

const known = (names, catalog) => names.filter((n) => NAME.test(n) && n in catalog);

/** Docker is installed when asked for or when a chosen persona needs it. */
export function dockerOn(catalog, c) {
  const personas = known(c.personas, catalog.linux.personas);
  return c.docker || personas.some((p) => catalog.linux.personas[p].docker);
}

/** The apps this machine would get before any are switched off: the installer's `when` rule. */
export function visibleApps(catalog, c) {
  const personas = known(c.personas, catalog.linux.personas);
  const listed = new Set(personas.flatMap((p) => catalog.linux.personas[p].apps));
  const holds = {
    desktop: c.role === "desktop",
    server: c.role === "server",
    heavy: c.heavy,
    docker: dockerOn(catalog, c),
    gpu: c.gpu,
  };
  return Object.entries(catalog.linux.apps)
    .filter(([name, app]) => app.when.every((w) => (w === "persona" ? listed.has(name) : holds[w])))
    .map(([name, app]) => ({ name, ...app }));
}

export function buildLinux(catalog, c, { plan = false, base = BASE_URL } = {}) {
  const personas = known(c.personas, catalog.linux.personas);
  const visible = new Set(visibleApps(catalog, c).map((a) => a.name));
  const skip = known(c.skip, catalog.linux.apps).filter((n) => visible.has(n));
  const harden = catalog.linux.harden.includes(c.harden) ? c.harden : "none";
  const args = [
    ...(plan ? ["plan"] : []),
    "--role",
    c.role === "server" ? "server" : "desktop",
    "--personas",
    personas.length ? personas.join(",") : "none",
    c.docker ? "--docker" : "--no-docker",
    c.gpu ? "--gpu" : "--no-gpu",
    c.heavy ? "--heavy" : "--no-heavy",
    "--harden",
    harden,
    ...(skip.length ? ["--skip-apps", skip.join(",")] : []),
  ];
  return `curl -fsSL ${base} | bash -s -- ${args.join(" ")}`;
}

export function buildWindows(catalog, personas, { plan = false, base = BASE_URL } = {}) {
  const chosen = known(personas, catalog.windows.personas);
  const args = ["-Persona", chosen.length ? chosen.join(",") : "none", ...(plan ? ["-ListPackages"] : [])];
  return `& ([scriptblock]::Create((irm ${base}/windows))) ${args.join(" ")}`;
}
