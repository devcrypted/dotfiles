import { buildLinux, buildWindows, defaults, dockerOn, visibleApps } from "./logic.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...kids);
  return node;
};

const state = { os: "linux", plan: false, linux: defaults(), windows: [] };
let catalog;

const ROLES = [["desktop", "Desktop"], ["server", "Server"]];
const HARDEN = [["none", "Off"], ["standard", "Standard"], ["aggressive", "Aggressive"]];

function segmented(host, options, value, onPick) {
  host.replaceChildren(
    ...options.map(([val, text]) => {
      const b = el("button", { type: "button", textContent: text, role: "radio" });
      b.setAttribute("aria-checked", String(val === value));
      b.onclick = () => onPick(val);
      return b;
    }),
  );
}

function chips(host, personas, selected, onToggle, dockerNote) {
  host.replaceChildren(
    ...Object.entries(personas).map(([name, p]) => {
      const input = el("input", { type: "checkbox", checked: selected.includes(name) });
      input.onchange = () => onToggle(name, input.checked);
      const tag = dockerNote && p.docker ? el("span", { className: "tag", textContent: "docker" }) : "";
      return el("label", { className: "chip" }, input, el("span", { className: "chip-body" }, el("b", { textContent: name }), el("small", { textContent: p.about }), tag));
    }),
  );
}

function renderLinux() {
  const c = state.linux;
  segmented($("role"), ROLES, c.role, (v) => { c.role = v; if (v === "server") c.heavy = false; render(); });
  segmented($("harden"), HARDEN, c.harden, (v) => { c.harden = v; render(); });

  const forced = dockerOn(catalog, { ...c, docker: false }) && !c.docker;
  const rows = [
    ["docker", "Docker", forced ? "Needed by a toolset you picked" : "Engine and Compose"],
    ["gpu", "NVIDIA GPU", "Driver and CUDA, only if a card is found"],
    ["heavy", "Heavy apps", "Large downloads; best with 8 GB+ RAM"],
  ];
  $("switches").replaceChildren(
    ...rows.map(([key, title, sub]) => {
      const on = key === "docker" ? dockerOn(catalog, c) : c[key];
      const input = el("input", { type: "checkbox", checked: on, disabled: key === "docker" && forced });
      input.onchange = () => { c[key] = input.checked; render(); };
      return el("label", { className: "switch" }, el("span", { className: "switch-text" }, el("b", { textContent: title }), el("small", { textContent: sub })), input, el("i", { className: "track", ariaHidden: "true" }));
    }),
  );

  chips($("personas-linux"), catalog.linux.personas, c.personas, (name, on) => {
    c.personas = on ? [...c.personas, name] : c.personas.filter((n) => n !== name);
    render();
  }, true);

  const apps = visibleApps(catalog, c);
  $("app-count").textContent = `${apps.filter((a) => !c.skip.includes(a.name)).length} of ${apps.length}`;
  $("apps").replaceChildren(
    ...apps.map((a) => {
      const input = el("input", { type: "checkbox", checked: !c.skip.includes(a.name) });
      input.onchange = () => { c.skip = input.checked ? c.skip.filter((n) => n !== a.name) : [...c.skip, a.name]; render(); };
      const tags = a.when.filter((w) => ["desktop", "heavy", "gpu", "docker"].includes(w)).map((w) => el("span", { className: "tag", textContent: w }));
      return el("li", {}, el("label", { className: "app" }, input, el("span", { className: "box", ariaHidden: "true" }), el("span", { className: "app-body" }, el("b", { textContent: a.name }), el("small", { textContent: a.about })), el("span", { className: "tags" }, ...tags)));
    }),
  );
}

function renderWindows() {
  chips($("personas-windows"), catalog.windows.personas, state.windows, (name, on) => {
    state.windows = on ? [...state.windows, name] : state.windows.filter((n) => n !== name);
    render();
  }, false);
}

function render() {
  const linux = state.os === "linux";
  for (const os of ["linux", "windows"]) {
    $(`tab-${os}`).setAttribute("aria-selected", String(state.os === os));
    $(`tab-${os}`).tabIndex = state.os === os ? 0 : -1;
    $(`panel-${os}`).hidden = state.os !== os;
  }
  $("shell-name").textContent = linux ? "bash" : "powershell";
  if (linux) {
    renderLinux();
    $("cmd").textContent = buildLinux(catalog, state.linux, { plan: state.plan });
    const c = state.linux;
    const apps = visibleApps(catalog, c).length - visibleApps(catalog, c).filter((a) => c.skip.includes(a.name)).length;
    $("summary").textContent = `${c.role}, ${c.personas.length || "no"} toolset${c.personas.length === 1 ? "" : "s"}, ${apps} apps`;
  } else {
    renderWindows();
    $("cmd").textContent = buildWindows(catalog, state.windows, { plan: state.plan });
    $("summary").textContent = `${state.windows.length || "no"} toolset${state.windows.length === 1 ? "" : "s"} on top of the base apps`;
  }
}

async function copy() {
  const btn = $("copy");
  const text = $("cmd").textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const range = document.createRange();
    range.selectNodeContents($("cmd"));
    const sel = getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand("copy");
  }
  btn.textContent = "Copied ✓";
  btn.classList.add("done");
  setTimeout(() => { btn.textContent = "Copy command"; btn.classList.remove("done"); }, 1800);
}

async function main() {
  try {
    catalog = await (await fetch("catalog.json")).json();
  } catch {
    $("cmd").textContent = "Could not load the catalogue. Reload, or use: curl -fsSL https://dot.kamal.sh | bash";
    return;
  }
  for (const os of ["linux", "windows"]) {
    $(`tab-${os}`).onclick = () => { state.os = os; render(); };
  }
  document.querySelector(".tabs").onkeydown = (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      state.os = state.os === "linux" ? "windows" : "linux";
      render();
      $(`tab-${state.os}`).focus();
    }
  };
  $("plan").onchange = (e) => { state.plan = e.target.checked; render(); };
  $("copy").onclick = copy;
  render();
}

main();
