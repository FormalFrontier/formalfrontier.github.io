import { initTheme, loadJSON, el, formatInt, formatCompact, setUpdated } from "./common.js";
import { lineChart, columnChart, heroSpark } from "./charts.js";

initTheme();

const data = await loadJSON("data/dashboard.json");
const { totals, history } = data;
setUpdated(data);

const n = history.days.length;
const weekAgo = Math.max(0, n - 8);
const change = (series) => series[n - 1] - series[weekAgo];
const sumLastWeek = (series) => series.slice(weekAgo + 1).reduce((a, b) => a + b, 0);
const signed = (value) => (value > 0 ? `+${formatInt(value)}` : `−${formatInt(-value)}`);
const weekly = (value, text = signed(value)) => (value ? `${text} in the last 7 days` : null);

document.getElementById("hero-value").textContent = formatInt(totals.lines);
const linesChange = change(history.lines);
if (linesChange) {
  document.getElementById("hero-delta").append(el("strong", { text: signed(linesChange) }), " in the last 7 days");
}
heroSpark(document.getElementById("hero-spark"), history.lines);

const tiles = [
  ["Libraries", totals.deliverables, weekly(change(history.deliverables))],
  ["Theorems and lemmas", totals.theorems, weekly(change(history.theorems))],
  ["Definitions", totals.definitions, weekly(change(history.definitions))],
  ["Releases", totals.releases, weekly(sumLastWeek(history.releases), formatInt(sumLastWeek(history.releases)))],
  ["Lean files", totals.files, null],
  ["Dependency links", totals.dependencies, null],
];
document.getElementById("tiles").append(
  ...tiles.map(([label, value, delta]) =>
    el(
      "div",
      { class: "card tile" },
      el("div", { class: "tile-label", text: label }),
      el("div", { class: "tile-value", text: formatCompact(value), title: formatInt(value) }),
      delta && el("div", { class: "delta", text: delta })
    )
  )
);

lineChart(document.getElementById("chart-libraries"), {
  days: history.days,
  values: history.deliverables,
  name: "libraries",
  description: "Released libraries by day",
});
lineChart(document.getElementById("chart-lines"), {
  days: history.days,
  values: history.lines,
  name: "lines",
  description: "Lines of Lean in released libraries by day",
});
lineChart(document.getElementById("chart-theorems"), {
  days: history.days,
  values: history.theorems,
  name: "theorems and lemmas",
  description: "Theorems and lemmas in released libraries by day",
});
columnChart(document.getElementById("chart-releases"), {
  days: history.days,
  values: history.releases,
  name: "releases",
  description: "Releases per day",
});

// Largest libraries: one horizontal bar per library, single hue, value at the tip.
const largest = [...data.deliverables].sort((a, b) => b.lines - a.lines).slice(0, 10);
const max = largest[0]?.lines || 1;
const rows = largest.map((d) => {
  const fill = el("div", { class: "hbar-fill" });
  fill.style.width = `calc((100% - 76px) * ${(d.lines / max).toFixed(4)})`;
  return el(
    "div",
    { class: "hbar-row" },
    el("a", { class: "hbar-name", href: `graph.html#${encodeURIComponent(d.name)}`, text: d.name }),
    el("div", { class: "hbar-track" }, fill, el("span", { class: "hbar-value", text: formatInt(d.lines) }))
  );
});
document.getElementById("largest").append(el("div", { class: "hbars" }, rows));
