// Shared helpers: theme toggle, data loading, formatting and small DOM builders.

const THEME_KEY = "ff-theme";

export function initTheme() {
  const root = document.documentElement;
  const button = document.querySelector(".theme-toggle");
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") root.dataset.theme = stored;
  const current = () =>
    root.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const label = () => {
    if (!button) return;
    const next = current() === "dark" ? "light" : "dark";
    button.setAttribute("aria-label", `Switch to ${next} theme`);
    button.title = `Switch to ${next} theme`;
  };
  label();
  button?.addEventListener("click", () => {
    const next = current() === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);
    label();
    document.dispatchEvent(new CustomEvent("themechange"));
  });
}

export async function loadJSON(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

const integer = new Intl.NumberFormat("en-US");
const compactFormat = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export const formatInt = (n) => integer.format(n);
export const formatCompact = (n) => (Math.abs(n) < 10000 ? integer.format(n) : compactFormat.format(n));

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function parseDay(day) {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function formatDay(day, withYear = true) {
  const date = parseDay(day);
  const text = `${MONTHS[date.getUTCMonth()]} ${date.getUTCDate()}`;
  return withYear ? `${text}, ${date.getUTCFullYear()}` : text;
}

// el("div", {class: "x"}, child, "text") builds elements; strings become text nodes.
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const SVG_NS = "http://www.w3.org/2000/svg";

export function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.setAttribute("class", value);
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child) node.append(child);
  }
  return node;
}

export function setUpdated(generated) {
  for (const node of document.querySelectorAll("[data-updated]")) {
    node.textContent = formatDay(generated);
  }
}

export function sparkline(points, { start, end, width = 96, height = 26 } = {}) {
  // points: [[day, value], ...] change points, drawn as steps on the [start, end] days.
  const node = svg("svg", { class: "spark", viewBox: `0 0 ${width} ${height}`, "aria-hidden": "true" });
  if (!points.length) return node;
  const t0 = parseDay(start ?? points[0][0]).getTime();
  const t1 = Math.max(parseDay(end ?? points[points.length - 1][0]).getTime(), t0 + 1);
  const max = Math.max(...points.map((p) => p[1]), 1);
  const x = (day) => 1 + ((parseDay(day).getTime() - t0) / (t1 - t0)) * (width - 2);
  const y = (v) => height - 2 - (v / max) * (height - 4);
  let d = `M${x(points[0][0]).toFixed(1)},${y(0).toFixed(1)}V${y(points[0][1]).toFixed(1)}`;
  for (const [day, value] of points.slice(1)) {
    d += `H${x(day).toFixed(1)}V${y(value).toFixed(1)}`;
  }
  d += `H${width - 1}`;
  const first = x(points[0][0]).toFixed(1);
  node.append(svg("path", { class: "spark-area", d: `${d}V${height}H${first}Z` }), svg("path", { d }));
  return node;
}
