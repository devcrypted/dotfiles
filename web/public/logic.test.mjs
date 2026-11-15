import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { buildLinux, buildWindows, defaults, visibleApps } from "./logic.js";

const catalog = JSON.parse(readFileSync(new URL("./catalog.json", import.meta.url)));
const names = (c) => visibleApps(catalog, c).map((a) => a.name);

test("a server never offers desktop apps", () => {
  const apps = names({ ...defaults(), role: "server" });
  assert.ok(!apps.includes("brave") && !apps.includes("vscode"));
  assert.ok(apps.includes("timeshift"));
});

test("heavy and gpu apps follow their switches", () => {
  assert.ok(names(defaults()).includes("jan"));
  assert.ok(!names({ ...defaults(), heavy: false }).includes("jan"));
  assert.ok(!names({ ...defaults(), gpu: false }).includes("nvtop"));
});

test("persona apps appear only with their persona", () => {
  assert.ok(!names(defaults()).includes("claude-code"));
  const withNode = names({ ...defaults(), personas: ["node"] });
  assert.ok(withNode.includes("claude-code"));
});

test("a persona that needs docker turns docker apps on", () => {
  const c = { ...defaults(), docker: false, personas: ["node"] };
  assert.ok(catalog.linux.personas.node.docker);
  assert.ok(names(c).includes("lazydocker"));
});

test("linux command carries every answer", () => {
  const c = { ...defaults(), role: "server", personas: ["node", "python"], gpu: false, skip: ["timeshift"] };
  assert.equal(
    buildLinux(catalog, c),
    "curl -fsSL https://dot.kamal.sh | bash -s -- --role server --personas node,python --docker --no-gpu --heavy --harden none --skip-apps timeshift",
  );
  assert.ok(buildLinux(catalog, c, { plan: true }).includes("-- plan --role server"));
});

test("only catalogue names reach a command", () => {
  const c = { ...defaults(), personas: ["node; rm -rf ~", "$(evil)"], skip: ["x y", "../etc"], harden: "x;y" };
  const cmd = buildLinux(catalog, c);
  assert.ok(cmd.includes("--personas none") && !cmd.includes("skip-apps") && cmd.endsWith("--harden none"));
  assert.ok(buildWindows(catalog, ["node;x", "$(y)"]).endsWith("-Persona none"));
});

test("skipping an app that is not offered is dropped", () => {
  const c = { ...defaults(), role: "server", skip: ["brave"] };
  assert.ok(!buildLinux(catalog, c).includes("skip-apps"));
});

test("windows command", () => {
  assert.equal(buildWindows(catalog, []), "& ([scriptblock]::Create((irm https://dot.kamal.sh/windows))) -Persona none");
  assert.equal(
    buildWindows(catalog, ["python", "node", "nope"], { plan: true }),
    "& ([scriptblock]::Create((irm https://dot.kamal.sh/windows))) -Persona python,node -ListPackages",
  );
});
