import { initTheme, loadJSON, el, setUpdated } from "./common.js";

initTheme();

const data = await loadJSON("data/highlights.json");
setUpdated(data);

const PREVIEW = 5;

// Trusted fragments: the updater escapes all README text and emits only a fixed
// set of tags, so these strings are safe to parse as HTML.
function fragment(html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  return template.content;
}

function sourceLine(sources) {
  if (!sources.length) return null;
  const seen = new Set();
  const parts = [];
  for (const s of sources) {
    const key = `${s.title}|${s.authors.join(",")}`;
    if (seen.has(key) || !s.title) continue;
    seen.add(key);
    const title = s.url ? el("a", { href: s.url }, el("em", { text: s.title })) : el("em", { text: s.title });
    parts.push(s.authors.length ? [s.authors.join(", "), ", ", title] : [title]);
  }
  if (!parts.length) return null;
  const line = el("p", { class: "sources" }, "Sources: ");
  parts.forEach((p, i) => {
    if (i) line.append("; ");
    line.append(...p);
  });
  return line;
}

function resultItem(item) {
  const link = item.link;
  return el(
    "li",
    {},
    el("span", { class: "r-title" }, fragment(item.title)),
    item.summary && el("span", { class: "r-summary" }, fragment(item.summary)),
    link && el("span", { class: "r-link" }, el("a", { href: link.url }, link.code ? el("code", { text: link.text }) : link.text))
  );
}

function clamped(text) {
  const body = el("p", { class: "desc clamp", text });
  const more = el("button", { class: "more inline", type: "button", text: "Show more", "aria-expanded": "false" });
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

function featuredCard(lib, h) {
  return el(
    "article",
    { class: "card lib-card" },
    el("div", { class: "lib-card-head" }, el("h2", { text: h.title })),
    el("p", { class: "desc" }, fragment(h.html)),
    h.declarations.length > 0 &&
      el(
        "p",
        { class: "sources" },
        h.declarations.flatMap((d, i) => [i ? ", " : "", el("a", { href: d.url }, el("code", { text: d.name }))])
      ),
    el("p", { class: "sources" }, "In ", el("a", { href: `#${encodeURIComponent(lib.name)}`, text: lib.title }))
  );
}

function card(lib) {
  const list = el("ul", { class: "results" }, lib.items.slice(0, PREVIEW).map(resultItem));
  const full = el("div", { class: "headline-full", hidden: true });
  const total = lib.items.length;
  const toggle = el("button", {
    class: "more",
    type: "button",
    "aria-expanded": "false",
    text: total > PREVIEW ? `Show all ${total} headline results` : "Show full statements",
  });
  toggle.addEventListener("click", async () => {
    const open = toggle.getAttribute("aria-expanded") === "true";
    if (!open && !full.childNodes.length) {
      toggle.disabled = true;
      try {
        const response = await fetch(`data/headlines/${encodeURIComponent(lib.name)}.html`, { cache: "no-cache" });
        full.append(fragment(response.ok ? await response.text() : "<p>Could not load the headline results.</p>"));
      } finally {
        toggle.disabled = false;
      }
    }
    full.hidden = open;
    list.hidden = !open;
    toggle.setAttribute("aria-expanded", String(!open));
    toggle.textContent = open
      ? total > PREVIEW ? `Show all ${total} headline results` : "Show full statements"
      : "Show summary";
  });
  return el(
    "article",
    { class: "card lib-card", id: lib.name },
    el(
      "div",
      { class: "lib-card-head" },
      el("h2", { text: lib.title }),
      el("a", { class: "repo", href: lib.url, text: lib.name })
    ),
    lib.description && clamped(lib.description),
    sourceLine(lib.sources),
    total ? list : el("p", { class: "none", text: "See the full headline results." }),
    full,
    toggle
  );
}

const libs = [...data.deliverables].sort((a, b) => a.title.localeCompare(b.title));
const featured = libs.flatMap((lib) => lib.highlights.map((h) => [lib, h]));
if (featured.length) {
  document.getElementById("featured-section").hidden = false;
  document.getElementById("featured").append(...featured.map(([lib, h]) => featuredCard(lib, h)));
}

const cards = libs.map((lib) => {
  const node = card(lib);
  const haystack = [lib.name, lib.title, lib.description, ...lib.items.map((i) => fragment(i.title).textContent)]
    .join(" ")
    .toLowerCase();
  return { node, haystack };
});
const container = document.getElementById("cards");
container.append(...cards.map((c) => c.node));

const count = document.getElementById("count");
const search = document.getElementById("search");
const filter = () => {
  const terms = search.value.toLowerCase().split(/\s+/).filter(Boolean);
  let shown = 0;
  for (const c of cards) {
    const match = terms.every((t) => c.haystack.includes(t));
    c.node.hidden = !match;
    if (match) shown += 1;
  }
  count.textContent = `${shown} of ${cards.length} libraries`;
};
search.addEventListener("input", filter);
filter();

if (location.hash) {
  document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView();
}
