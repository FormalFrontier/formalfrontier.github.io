import { initTheme, loadJSON, el, formatInt, formatDay, setUpdated, sparkline } from "./common.js";

initTheme();

const data = await loadJSON("data/dashboard.json");
setUpdated(data);
const start = data.history.days[0];
const end = data.generated;
const maxLines = Math.max(...data.deliverables.map((d) => d.lines), 1);

const COLUMNS = [
  { key: "name", label: "Library", type: "text" },
  { key: "lines", label: "Lines of Lean", type: "num" },
  { key: "growth", label: "Growth", type: "spark" },
  { key: "theorems", label: "Theorems", type: "num" },
  { key: "definitions", label: "Definitions", type: "num" },
  { key: "releases", label: "Releases", type: "num" },
  { key: "deps", label: "Uses", type: "count" },
  { key: "dependents", label: "Used by", type: "count" },
  { key: "first_release", label: "First release", type: "date" },
  { key: "last_release", label: "Latest", type: "date" },
];

let sortKey = "lines";
let sortDir = -1;

function value(d, key) {
  const v = d[key];
  return Array.isArray(v) ? v.length : v;
}

function cell(d, column) {
  switch (column.type) {
    case "text":
      return el(
        "td",
        {},
        el("div", { class: "lib-name" }, el("a", { href: d.url, text: d.name })),
        d.title.toLowerCase().replace(/[^a-z0-9]/g, "") !== d.name.replace(/[^a-z0-9]/g, "") && el("div", { class: "lib-title", text: d.title })
      );
    case "num":
      if (column.key === "lines") {
        const fill = el("div", { class: "bar-fill" });
        fill.style.width = `${((d.lines / maxLines) * 100).toFixed(2)}%`;
        return el(
          "td",
          { class: "num" },
          el("div", { class: "bar-cell" }, formatInt(d.lines), el("div", { class: "bar-track", "aria-hidden": "true" }, fill))
        );
      }
      return el("td", { class: "num", text: formatInt(d[column.key]) });
    case "spark":
      return el("td", {}, sparkline(d.series, { start, end }));
    case "count":
      return el("td", { class: "num" }, el("a", { href: `graph.html#${encodeURIComponent(d.name)}`, text: String(d[column.key].length) }));
    case "date":
      return el("td", { class: "num", text: formatDay(d[column.key], d[column.key].slice(0, 4) !== end.slice(0, 4)) });
  }
}

const table = el("table", { class: "lib-table" });
const head = el("thead");
const body = el("tbody");
table.append(head, body);
document.getElementById("table").append(table);

function renderHead() {
  head.replaceChildren(
    el(
      "tr",
      {},
      COLUMNS.map((c) => {
        if (c.type === "spark") return el("th", { text: c.label });
        const th = el("th", {
          class: c.type === "text" ? "" : "num",
          "aria-sort": sortKey === c.key ? (sortDir > 0 ? "ascending" : "descending") : "none",
        });
        th.append(
          el("button", {
            type: "button",
            text: c.label,
            onclick: () => {
              if (sortKey === c.key) sortDir = -sortDir;
              else {
                sortKey = c.key;
                sortDir = c.type === "text" ? 1 : -1;
              }
              render();
            },
          })
        );
        return th;
      })
    )
  );
}

const search = document.getElementById("search");
const count = document.getElementById("count");

function render() {
  renderHead();
  const terms = search.value.toLowerCase().split(/\s+/).filter(Boolean);
  const rows = data.deliverables
    .filter((d) => {
      const text = `${d.name} ${d.title} ${d.description}`.toLowerCase();
      return terms.every((t) => text.includes(t));
    })
    .sort((a, b) => {
      const x = value(a, sortKey);
      const y = value(b, sortKey);
      const order = typeof x === "string" ? x.localeCompare(y) : x - y;
      return order * sortDir || a.name.localeCompare(b.name);
    });
  body.replaceChildren(...rows.map((d) => el("tr", {}, COLUMNS.map((c) => cell(d, c)))));
  count.textContent = `${rows.length} of ${data.deliverables.length} libraries`;
}

search.addEventListener("input", render);
render();
