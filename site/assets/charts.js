// Single-series time charts: a line (with area wash) and daily columns.
// Both carry a crosshair or per-column tooltip, keyboard stepping and a table view.

import { el, svg, formatInt, formatCompact, formatDay, parseDay } from "./common.js";

const MARGIN = { top: 14, right: 64, bottom: 30, left: 52 };
const HEIGHT = 230;

function niceStep(max, count) {
  const raw = max / count;
  const power = 10 ** Math.floor(Math.log10(raw || 1));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (m * power >= raw) return m * power;
  }
  return 10 * power;
}

function yTicks(max) {
  const step = niceStep(Math.max(max, 1), 4);
  const top = Math.ceil(Math.max(max, 1) / step) * step;
  const ticks = [];
  for (let v = 0; v <= top + step / 2; v += step) ticks.push(v);
  return { ticks, top };
}

function xTicks(days, width) {
  // Weekly or wider ticks on Mondays, thinned to fit.
  const maxTicks = Math.max(2, Math.floor(width / 90));
  const mondays = days.map((d, i) => [d, i]).filter(([d]) => parseDay(d).getUTCDay() === 1);
  let every = 1;
  while (mondays.length / every > maxTicks) every += 1;
  return mondays.filter((_, k) => k % every === 0).map(([, i]) => i);
}

function tableView(caption, days, values, valueLabel) {
  const rows = days.map((day, i) =>
    el("tr", {}, el("td", { text: formatDay(day) }), el("td", { class: "num", text: formatInt(values[i]) }))
  ).reverse();
  return el(
    "details",
    { class: "table-view" },
    el("summary", { text: "Table view" }),
    el(
      "div",
      { class: "table-scroll" },
      el(
        "table",
        {},
        el("caption", { class: "visually-hidden", text: caption }),
        el("thead", {}, el("tr", {}, el("th", { text: "Date" }), el("th", { class: "num", text: valueLabel }))),
        el("tbody", {}, rows)
      )
    )
  );
}

function tooltip(container) {
  const node = el("div", { class: "tooltip", role: "status", "aria-live": "polite" });
  container.append(node);
  return {
    show(day, value, name, x, y) {
      node.replaceChildren(
        el("div", { class: "tt-date", text: formatDay(day) }),
        el(
          "div",
          { class: "tt-row" },
          el("span", { class: "tt-key" }),
          el("span", { class: "tt-value", text: formatInt(value) }),
          el("span", { class: "tt-name", text: name })
        )
      );
      node.classList.add("is-visible");
      const box = container.getBoundingClientRect();
      const w = node.offsetWidth;
      const left = x + 14 + w > box.width ? x - 14 - w : x + 14;
      node.style.left = `${Math.max(0, left)}px`;
      node.style.top = `${Math.max(0, y - 44)}px`;
    },
    hide() {
      node.classList.remove("is-visible");
    },
  };
}

function frame(container, days, max, bands = false) {
  const width = Math.max(280, container.clientWidth);
  const plotW = width - MARGIN.left - MARGIN.right;
  const plotH = HEIGHT - MARGIN.top - MARGIN.bottom;
  const { ticks, top } = yTicks(max);
  const x = bands
    ? (i) => MARGIN.left + ((i + 0.5) / days.length) * plotW
    : (i) => MARGIN.left + (days.length === 1 ? plotW / 2 : (i / (days.length - 1)) * plotW);
  const y = (v) => MARGIN.top + plotH - (v / top) * plotH;
  const root = svg("svg", {
    viewBox: `0 0 ${width} ${HEIGHT}`,
    height: HEIGHT,
    role: "img",
    tabindex: "0",
  });
  const axis = svg("g", { class: "axis" });
  for (const v of ticks) {
    axis.append(
      svg("line", { class: v === 0 ? "base-line" : "grid-line", x1: MARGIN.left, x2: width - MARGIN.right, y1: y(v), y2: y(v) }),
      svg("text", { x: MARGIN.left - 8, y: y(v) + 4, "text-anchor": "end", text: formatCompact(v) })
    );
  }
  for (const i of xTicks(days, plotW)) {
    axis.append(svg("text", { x: x(i), y: HEIGHT - 8, "text-anchor": "middle", text: formatDay(days[i], false) }));
  }
  root.append(axis);
  return { root, width, plotW, plotH, x, y };
}

function mount(container, render) {
  let last = 0;
  const draw = () => {
    const w = container.clientWidth;
    if (w && w !== last) {
      last = w;
      render();
    }
  };
  new ResizeObserver(draw).observe(container);
  draw();
}

export function lineChart(container, { days, values, name, description }) {
  const plot = el("div", { class: "chart" });
  container.append(plot, tableView(description, days, values, name));
  mount(plot, () => {
    plot.replaceChildren();
    const max = Math.max(...values);
    const f = frame(plot, days, max);
    f.root.setAttribute("aria-label", `${description}. Latest: ${formatInt(values[values.length - 1])}.`);
    let line = "";
    values.forEach((v, i) => {
      line += `${i ? "L" : "M"}${f.x(i).toFixed(1)},${f.y(v).toFixed(1)}`;
    });
    const area = `${line}L${f.x(values.length - 1).toFixed(1)},${f.y(0)}L${f.x(0).toFixed(1)},${f.y(0)}Z`;
    const last = values.length - 1;
    const cross = svg("line", { class: "crosshair", y1: 14, y2: HEIGHT - 30, visibility: "hidden" });
    const dot = svg("circle", { class: "end-dot", r: 4.5, visibility: "hidden" });
    f.root.append(
      svg("path", { class: "series-area", d: area }),
      svg("path", { class: "series-line", d: line }),
      svg("circle", { class: "end-dot", cx: f.x(last), cy: f.y(values[last]), r: 4.5 }),
      svg("text", {
        class: "end-label",
        x: f.x(last) + 9,
        y: f.y(values[last]) + 4,
        text: formatCompact(values[last]),
      }),
      cross,
      dot
    );
    plot.append(f.root);
    const tip = tooltip(plot);
    let index = last;
    const show = (i) => {
      index = Math.max(0, Math.min(last, i));
      const cx = f.x(index);
      const cy = f.y(values[index]);
      cross.setAttribute("x1", cx);
      cross.setAttribute("x2", cx);
      cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", cx);
      dot.setAttribute("cy", cy);
      dot.setAttribute("visibility", "visible");
      tip.show(days[index], values[index], name, (cx / f.width) * plot.clientWidth, cy);
    };
    const hide = () => {
      cross.setAttribute("visibility", "hidden");
      dot.setAttribute("visibility", "hidden");
      tip.hide();
    };
    f.root.addEventListener("pointermove", (event) => {
      const box = f.root.getBoundingClientRect();
      const px = ((event.clientX - box.left) / box.width) * f.width;
      const ratio = (px - f.x(0)) / Math.max(1, f.x(last) - f.x(0));
      show(Math.round(ratio * last));
    });
    f.root.addEventListener("pointerleave", hide);
    f.root.addEventListener("focus", () => show(index));
    f.root.addEventListener("blur", hide);
    f.root.addEventListener("keydown", (event) => {
      const step = { ArrowLeft: -1, ArrowRight: 1, Home: -Infinity, End: Infinity }[event.key];
      if (step === undefined) return;
      event.preventDefault();
      show(Number.isFinite(step) ? index + step : step < 0 ? 0 : last);
    });
  });
}

export function columnChart(container, { days, values, name, description }) {
  const plot = el("div", { class: "chart" });
  container.append(plot, tableView(description, days, values, name));
  mount(plot, () => {
    plot.replaceChildren();
    const max = Math.max(...values);
    const f = frame(plot, days, max, true);
    f.root.setAttribute("aria-label", `${description}. Latest: ${formatInt(values[values.length - 1])}.`);
    const band = f.plotW / days.length;
    const barW = Math.max(2, Math.min(24, band - 2));
    const tip = tooltip(plot);
    const bars = [];
    const bottom = f.y(0);
    values.forEach((v, i) => {
      const cx = f.x(i);
      const top = f.y(v);
      const h = bottom - top;
      const r = Math.min(4, barW / 2, h);
      const x0 = cx - barW / 2;
      const d = h <= 0 ? "" :
        `M${x0},${bottom}V${top + r}Q${x0},${top} ${x0 + r},${top}H${x0 + barW - r}` +
        `Q${x0 + barW},${top} ${x0 + barW},${top + r}V${bottom}Z`;
      const bar = svg("path", { class: "series-bar", d });
      const hit = svg("rect", {
        x: cx - band / 2,
        y: 14,
        width: band,
        height: bottom - 14,
        fill: "transparent",
      });
      const enter = () => {
        bars.forEach((b) => b.classList.remove("is-hover"));
        bar.classList.add("is-hover");
        tip.show(days[i], v, name, (cx / f.width) * plot.clientWidth, top);
      };
      hit.addEventListener("pointerenter", enter);
      hit.addEventListener("pointerleave", () => {
        bar.classList.remove("is-hover");
        tip.hide();
      });
      bars.push(bar);
      f.root.append(bar, hit);
      bar.enter = enter;
    });
    let index = values.length - 1;
    f.root.addEventListener("focus", () => bars[index].enter());
    f.root.addEventListener("blur", () => {
      bars.forEach((b) => b.classList.remove("is-hover"));
      tip.hide();
    });
    f.root.addEventListener("keydown", (event) => {
      const step = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
      if (!step) return;
      event.preventDefault();
      index = Math.max(0, Math.min(values.length - 1, index + step));
      bars[index].enter();
    });
    plot.append(f.root);
  });
}

export function heroSpark(container, values) {
  // Drawn at the container's measured size so it can fill the card without distortion.
  const draw = () => {
    const width = Math.max(container.clientWidth, 120);
    const height = Math.max(container.clientHeight, 72);
    const max = Math.max(...values, 1);
    const x = (i) => (values.length === 1 ? width / 2 : (i / (values.length - 1)) * (width - 10) + 2);
    const y = (v) => height - 2 - (v / max) * (height - 12);
    let line = "";
    values.forEach((v, i) => {
      line += `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    });
    const last = values.length - 1;
    container.replaceChildren(
      svg(
        "svg",
        { class: "hero-spark", width, height, viewBox: `0 0 ${width} ${height}`, "aria-hidden": "true" },
        svg("path", { class: "series-area", d: `${line}L${x(last)},${height}L${x(0)},${height}Z` }),
        svg("path", { class: "series-line", d: line }),
        svg("circle", { class: "end-dot", cx: x(last), cy: y(values[last]), r: 4 })
      )
    );
  };
  let size = "";
  new ResizeObserver(() => {
    const next = `${container.clientWidth}x${container.clientHeight}`;
    if (next !== size) {
      size = next;
      draw();
    }
  }).observe(container);
}
