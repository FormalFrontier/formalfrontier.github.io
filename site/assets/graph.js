import { initTheme, loadJSON, el, svg, formatInt, formatDay, setUpdated } from "./common.js";

initTheme();

const data = await loadJSON("data/dashboard.json");
setUpdated(data);
const { graph } = data;
const libraries = new Map(data.deliverables.map((d) => [d.name, d]));

function closure(start, next) {
  const seen = new Set();
  const stack = [...next(start)];
  while (stack.length) {
    const name = stack.pop();
    if (seen.has(name) || name === start) continue;
    seen.add(name);
    stack.push(...next(name));
  }
  return seen;
}
const upstream = (name) => closure(name, (n) => libraries.get(n)?.deps ?? []);
const downstream = (name) => closure(name, (n) => libraries.get(n)?.dependents ?? []);

// Drawing
const PAD = 16;
const LINE = 15;
const root = svg("svg", {
  class: "graph-svg",
  viewBox: `${-PAD} ${-PAD} ${graph.width + 2 * PAD} ${graph.height + 2 * PAD}`,
  role: "group",
  "aria-label": `Dependency graph of ${graph.nodes.length} libraries`,
});
const edgeLayer = svg("g");
const nodeLayer = svg("g");

if (graph.isolated) {
  const rowNodes = graph.nodes.filter((n) => n.row === graph.rows - 1);
  const top = Math.min(...rowNodes.map((n) => n.y - n.h / 2)) - 14;
  root.append(
    svg("line", { class: "row-rule", x1: 0, x2: graph.width, y1: top, y2: top }),
    svg("text", { class: "row-label", x: 0, y: top - 8, text: "No dependency links within the project" })
  );
}

function curve(points) {
  let d = `M${points[0][0]},${points[0][1]}`;
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const my = (y0 + y1) / 2;
    d += `C${x0},${my} ${x1},${my} ${x1},${y1}`;
  }
  return d;
}

const edges = graph.edges.map((edge) => {
  const path = svg("path", { class: edge.cycle ? "edge cycle" : "edge", d: curve(edge.points) });
  edgeLayer.append(path);
  return { ...edge, path };
});

const nodes = new Map();
for (const node of graph.nodes) {
  const lib = libraries.get(node.name);
  const g = svg("g", {
    class: "node",
    tabindex: "0",
    role: "button",
    "aria-label": `${node.name}: ${lib.deps.length} direct dependencies, ${lib.dependents.length} direct dependents`,
    transform: `translate(${node.x},${node.y})`,
  });
  g.append(
    svg("rect", { x: -node.w / 2, y: -node.h / 2, width: node.w, height: node.h, rx: 8 }),
    svg("rect", { class: "ring", x: -node.w / 2 + 3, y: -node.h / 2 + 3, width: node.w - 6, height: node.h - 6, rx: 6 })
  );
  const first = -((node.lines.length - 1) * LINE) / 2;
  node.lines.forEach((line, i) => {
    g.append(svg("text", { x: 0, y: first + i * LINE + 4.5, "text-anchor": "middle", text: line }));
  });
  g.addEventListener("pointerenter", () => preview(node.name));
  g.addEventListener("pointerleave", () => preview(null));
  g.addEventListener("click", () => select(selected === node.name ? null : node.name));
  g.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select(selected === node.name ? null : node.name);
    }
  });
  nodeLayer.append(g);
  nodes.set(node.name, g);
}
root.append(edgeLayer, nodeLayer);
document.getElementById("graph").append(root);

// Focus state
let selected = null;

function paint(name) {
  root.classList.toggle("has-focus", Boolean(name));
  const up = name ? upstream(name) : new Set();
  const down = name ? downstream(name) : new Set();
  for (const [n, g] of nodes) {
    g.classList.toggle("focus", n === name);
    // In a dependency cycle a library can be both upstream and downstream.
    g.classList.toggle("both", up.has(n) && down.has(n));
    g.classList.toggle("dep", up.has(n) && !down.has(n));
    g.classList.toggle("use", down.has(n) && !up.has(n));
    g.setAttribute("aria-pressed", String(n === selected));
  }
  for (const edge of edges) {
    const dep = Boolean(name) && (edge.from === name || up.has(edge.from)) && up.has(edge.to);
    const use = Boolean(name) && down.has(edge.from) && (edge.to === name || down.has(edge.to));
    edge.path.classList.toggle("dep", dep);
    edge.path.classList.toggle("use", use);
    if (dep || use) edgeLayer.append(edge.path);
  }
}

function preview(name) {
  paint(name ?? selected);
}

function select(name) {
  selected = name;
  paint(name);
  renderPanel(name);
  const hash = name ? `#${encodeURIComponent(name)}` : " ";
  history.replaceState(null, "", hash === " " ? location.pathname : hash);
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && selected) select(null);
});

// Side panel
const panel = document.getElementById("panel");

function chips(names, kind) {
  if (!names.length) return el("div", { class: "none", text: "None" });
  return el(
    "div",
    { class: "chips" },
    names.map((n) =>
      el("button", { class: `chip ${kind}`, type: "button", onclick: () => select(n) }, el("span", { class: "chip-key" }), n)
    )
  );
}

function description(text) {
  if (!text) return [];
  const body = el("p", { class: "clamp", text });
  const more = el("button", { class: "more", type: "button", text: "Show more", "aria-expanded": "false" });
  more.addEventListener("click", () => {
    const open = body.classList.toggle("open");
    more.textContent = open ? "Show less" : "Show more";
    more.setAttribute("aria-expanded", String(open));
  });
  // Only offer the toggle when the text is actually clamped.
  requestAnimationFrame(() => {
    if (body.scrollHeight <= body.clientHeight + 1) more.remove();
  });
  return [body, more];
}

function renderPanel(name) {
  if (!name) {
    const roots = data.deliverables.filter((d) => !d.deps.length && d.dependents.length).length;
    panel.replaceChildren(
      el("h2", { text: `${formatInt(data.deliverables.length)} libraries` }),
      el("p", {
        text: `${formatInt(data.totals.dependencies)} direct dependency links. ${roots} foundation libraries have dependents but no project dependencies. Select a library to see what it builds on and what builds on it.`,
      })
    );
    return;
  }
  const lib = libraries.get(name);
  const up = upstream(name);
  const down = downstream(name);
  panel.replaceChildren(
    el("h2", { text: lib.name }),
    el("div", { class: "panel-title", text: lib.title }),
    ...description(lib.description),
    el(
      "dl",
      {},
      el("dt", { text: "Lines of Lean" }),
      el("dd", { text: formatInt(lib.lines) }),
      el("dt", { text: "Theorems and lemmas" }),
      el("dd", { text: formatInt(lib.theorems) }),
      el("dt", { text: "Definitions" }),
      el("dd", { text: formatInt(lib.definitions) }),
      el("dt", { text: "Releases" }),
      el("dd", { text: formatInt(lib.releases) }),
      el("dt", { text: "First release" }),
      el("dd", { text: formatDay(lib.first_release) }),
      el("dt", { text: "Latest release" }),
      el("dd", { text: formatDay(lib.last_release) })
    ),
    el("h3", { text: `Depends on directly (${lib.deps.length}; ${up.size} at all levels)` }),
    chips(lib.deps, "dep"),
    el("h3", { text: `Used directly by (${lib.dependents.length}; ${down.size} at all levels)` }),
    chips(lib.dependents, "use"),
    lib.external_deps.length > 0 && el("h3", { text: "Other dependencies" }),
    lib.external_deps.length > 0 && el("div", { class: "none", text: lib.external_deps.join(", ") }),
    el(
      "div",
      { class: "panel-links" },
      el("a", { href: lib.url, text: "Repository" }),
      el("a", { href: `highlights.html#${encodeURIComponent(lib.name)}`, text: "Headline results" })
    )
  );
}

// Table view
const sorted = [...data.deliverables].sort((a, b) => a.name.localeCompare(b.name));
document.getElementById("graph-table").append(
  el(
    "table",
    {},
    el("thead", {}, el("tr", {}, el("th", { text: "Library" }), el("th", { text: "Depends on" }), el("th", { text: "Used by" }))),
    el(
      "tbody",
      {},
      sorted.map((d) =>
        el(
          "tr",
          {},
          el("td", {}, el("a", { href: d.url, text: d.name })),
          el("td", { text: d.deps.join(", ") || "—" }),
          el("td", { text: d.dependents.join(", ") || "—" })
        )
      )
    )
  )
);

if (!graph.edges.some((e) => e.cycle)) document.getElementById("legend-both").hidden = true;

const initial = decodeURIComponent(location.hash.slice(1));
select(libraries.has(initial) ? initial : null);
if (libraries.has(initial)) {
  // Bring the node into view horizontally when the graph is wider than its card.
  const card = document.getElementById("graph");
  const box = nodes.get(initial).getBoundingClientRect();
  const frame = card.getBoundingClientRect();
  card.scrollLeft += box.left + box.width / 2 - (frame.left + frame.width / 2);
}
