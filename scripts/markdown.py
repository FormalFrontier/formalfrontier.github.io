"""A small, safe Markdown renderer for README sections.

It supports the subset the deliverable READMEs use: headings, paragraphs,
bullet and numbered lists, fenced code, tables, code spans, links, bold and
italic. All other text, including raw HTML, is escaped. Relative links become
GitHub permalinks at the released commit.
"""

from __future__ import annotations

import html
import posixpath
import re
from dataclasses import dataclass, field

FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([\w+-]*)")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
ITEM_RE = re.compile(r"^(\s{0,3})([-*+]|\d{1,9}[.)])(\s+)(.*)$")
TABLE_RULE_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
ANCHOR_RE = re.compile(r'^\s*(<a id="[^"]*"></a>\s*)+$')
CODE_RE = re.compile(r"(`+)(.+?)(?<!`)\1(?!`)", re.DOTALL)
LINK_RE = re.compile(
    r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(\s*<?([^()\s<>]*(?:\([^()\s]*\)[^()\s<>]*)*)>?"
    r"(?:\s+\"[^\"]*\")?\s*\)"
)
ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|<>~])")
MARK = "\x00"
MARK_RE = re.compile(MARK + r"(\d+)" + MARK)


@dataclass
class Links:
    """Resolves README links against one released commit of one repository."""

    org: str
    repo: str
    sha: str
    base: str = ""
    dirs: set = field(default_factory=set)

    def resolve(self, url: str) -> str | None:
        if re.match(r"^https?://", url):
            return url
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url) or url.startswith("//"):
            return None
        root = f"https://github.com/{self.org}/{self.repo}"
        path, _, fragment = url.partition("#")
        fragment = f"#{fragment}" if fragment else ""
        if not path:
            return f"{root}/blob/{self.sha}/README.md{fragment}"
        path = posixpath.normpath(posixpath.join(self.base, path.lstrip("/")))
        if path.startswith(".."):
            return None
        if path == ".":
            return f"{root}/tree/{self.sha}{fragment}"
        kind = "tree" if path in self.dirs else "blob"
        return f"{root}/{kind}/{self.sha}/{path}{fragment}"


def section(markdown: str, title: str) -> str:
    """The body of the `## title` section, without its heading."""
    out = []
    inside = False
    fence = None
    for line in markdown.split("\n"):
        match = FENCE_RE.match(line)
        if fence is not None:
            if match and match.group(2)[0] == fence:
                fence = None
        elif match:
            fence = match.group(2)[0]
        else:
            heading = HEADING_RE.match(line)
            if heading and len(heading.group(1)) <= 2:
                if inside:
                    break
                if heading.group(2).strip().lower() == title.lower():
                    inside = True
                    continue
        if inside:
            out.append(line)
    return "\n".join(out).strip("\n")


def inline(text: str, links: Links) -> str:
    saved: list[str] = []

    def keep(fragment: str) -> str:
        saved.append(fragment)
        return f"{MARK}{len(saved) - 1}{MARK}"

    def code(match: re.Match) -> str:
        body = match.group(2).replace("\n", " ")
        if body.startswith(" ") and body.endswith(" ") and body.strip():
            body = body[1:-1]
        return keep(f"<code>{html.escape(body)}</code>")

    def link(match: re.Match) -> str:
        label = emphasis(html.escape(match.group(1), quote=False))
        target = links.resolve(match.group(2))
        if target is None:
            return keep(label)
        return keep(f'<a href="{html.escape(target)}">{label}</a>')

    text = text.replace(MARK, "")
    text = CODE_RE.sub(code, text)
    text = ESCAPE_RE.sub(lambda m: keep(html.escape(m.group(1))), text)
    text = LINK_RE.sub(link, text)
    text = emphasis(html.escape(text, quote=False))
    while MARK_RE.search(text):
        text = MARK_RE.sub(lambda m: saved[int(m.group(1))], text)
    return text


def emphasis(text: str) -> str:
    text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", text, flags=re.DOTALL)
    text = re.sub(r"(?<![\w*])__(?=\S)(.+?)(?<=\S)__(?![\w*])", r"<strong>\1</strong>", text,
                  flags=re.DOTALL)
    text = re.sub(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])", r"<em>\1</em>", text,
                  flags=re.DOTALL)
    text = re.sub(r"(?<![\w_])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])", r"<em>\1</em>", text,
                  flags=re.DOTALL)
    return text


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _starts_block(line: str) -> bool:
    return bool(FENCE_RE.match(line) or HEADING_RE.match(line) or ITEM_RE.match(line))


def blocks(lines: list[str]) -> list[tuple]:
    """Parse lines into (kind, ...) block tuples."""
    out: list[tuple] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or ANCHOR_RE.match(line):
            i += 1
            continue
        fence = FENCE_RE.match(line)
        if fence:
            indent, marker, lang = len(fence.group(1)), fence.group(2), fence.group(3)
            body = []
            i += 1
            while i < len(lines):
                close = FENCE_RE.match(lines[i])
                if close and close.group(2)[0] == marker[0] and len(close.group(2)) >= len(marker) \
                        and not close.group(3):
                    i += 1
                    break
                body.append(lines[i][min(indent, _indent(lines[i])):])
                i += 1
            out.append(("code", lang, "\n".join(body)))
            continue
        heading = HEADING_RE.match(line)
        if heading:
            out.append(("heading", len(heading.group(1)), heading.group(2)))
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and TABLE_RULE_RE.match(lines[i + 1]):
            rows = [line]
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(("table", rows))
            continue
        item = ITEM_RE.match(line)
        if item:
            ordered = item.group(2)[0].isdigit()
            items = []
            while i < len(lines):
                item = ITEM_RE.match(lines[i])
                if not item or item.group(2)[0].isdigit() != ordered:
                    break
                width = len(item.group(1)) + len(item.group(2)) + len(item.group(3))
                content = [item.group(4)]
                i += 1
                loose = False
                while i < len(lines):
                    nxt = lines[i]
                    if not nxt.strip():
                        if i + 1 < len(lines) and lines[i + 1].strip() and _indent(lines[i + 1]) >= 2:
                            content.append("")
                            loose = True
                            i += 1
                            continue
                        break
                    if _indent(nxt) >= 2:
                        content.append(nxt[min(width, _indent(nxt)):])
                    elif ITEM_RE.match(nxt) or _starts_block(nxt):
                        break
                    elif content and content[-1].strip():
                        content.append(nxt)
                    else:
                        break
                    i += 1
                items.append((blocks(content), loose))
                if i < len(lines) and not lines[i].strip():
                    j = i
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and ITEM_RE.match(lines[j]) and _indent(lines[j]) < 2:
                        i = j
                        continue
                    break
            out.append(("list", ordered, items))
            continue
        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not _starts_block(lines[i]) \
                and not ANCHOR_RE.match(lines[i]):
            para.append(lines[i])
            i += 1
        out.append(("paragraph", "\n".join(s.strip() for s in para)))
    return out


def _cells(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", row)]


def _html(parsed: list[tuple], links: Links, tight: bool = False) -> str:
    parts = []
    for block in parsed:
        kind = block[0]
        if kind == "paragraph":
            body = inline(block[1], links)
            parts.append(body if tight else f"<p>{body}</p>")
        elif kind == "heading":
            level = min(6, block[1] + 1)
            parts.append(f"<h{level}>{inline(block[2], links)}</h{level}>")
        elif kind == "code":
            lang = f' class="language-{html.escape(block[1])}"' if block[1] else ""
            parts.append(f"<pre><code{lang}>{html.escape(block[2])}</code></pre>")
        elif kind == "table":
            head, *rows = block[1]
            cells = "".join(f"<th>{inline(c, links)}</th>" for c in _cells(head))
            body = "".join(
                "<tr>" + "".join(f"<td>{inline(c, links)}</td>" for c in _cells(r)) + "</tr>"
                for r in rows
            )
            parts.append(f'<div class="table-wrap"><table><thead><tr>{cells}</tr></thead>'
                         f"<tbody>{body}</tbody></table></div>")
        elif kind == "list":
            tag = "ol" if block[1] else "ul"
            entries = []
            for content, loose in block[2]:
                single = len(content) == 1 and content[0][0] == "paragraph"
                entries.append(f"<li>{_html(content, links, tight=single and not loose)}</li>")
            parts.append(f"<{tag}>{''.join(entries)}</{tag}>")
    return "\n".join(parts)


def render(markdown: str, links: Links) -> str:
    return _html(blocks(markdown.split("\n")), links)


_ABBREVIATIONS = {"e.g.", "i.e.", "cf.", "resp.", "vs."}


def _first_sentence(text: str, limit: int = 140, stops: str = ".:;") -> str:
    """The first sentence of Markdown text, cut at a word outside code spans."""
    flat = " ".join(text.split())
    in_code = False
    end = len(flat)
    cut = None
    for i, ch in enumerate(flat):
        if ch == "`":
            in_code = not in_code
        elif in_code:
            continue
        elif ch == " " and i <= limit:
            cut = i
        elif ch in stops and (i + 1 == len(flat) or flat[i + 1] == " "):
            if flat[: i + 1].rsplit(" ", 1)[-1].lower() not in _ABBREVIATIONS:
                end = i + 1
                break
    sentence = flat[:end]
    if len(sentence) > limit and cut:
        sentence = flat[:cut].rstrip(",;:") + " …"
    return sentence


_END = re.compile(r"(?<!\.)[.:;]$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _item_link(text: str, links: Links) -> dict | None:
    """The result's declaration link, else the last link into the repository."""
    code_link = re.search(r"\[`([^`\]]+)`\]\(([^)\s]+)\)", text)
    if code_link:
        target = links.resolve(code_link.group(2))
        if target:
            return {"text": code_link.group(1), "url": target, "code": True}
    local = [m for m in _LINK.finditer(text) if not re.match(r"[a-z][a-z0-9+.-]*:", m.group(2), re.I)]
    for match in reversed(local):
        target = links.resolve(match.group(2))
        if target and match.group(1).strip("`"):
            label = match.group(1)
            return {"text": label.strip("`"), "url": target, "code": label.startswith("`")}
    return None


def _summary(rest: str, links: Links) -> str | None:
    rest = rest.lstrip(" :;,.—–-")
    if not rest or re.match(r"(see|cf\.)\s", rest, re.I):
        return None
    return inline(_first_sentence(rest, 220, stops="."), links)


def items(markdown: str, links: Links) -> list[dict]:
    """One entry per headline result: a short title, a summary, its group and a link."""
    out = []
    group = None
    for block in blocks(markdown.split("\n")):
        if block[0] == "heading":
            group = inline(block[2], links)
            out.append({"title": group, "summary": None, "group": None, "link": None, "heading": True})
        elif block[0] == "list":
            for content, _ in block[2]:
                if not content or content[0][0] != "paragraph":
                    continue
                text = " ".join(content[0][1].split())
                bold = re.match(r"^\*\*(.+?)\*\*", text)
                link = _LINK.match(text)
                summary = None
                if bold:
                    title = inline(_END.sub("", bold.group(1).strip()), links)
                    summary = _summary(text[bold.end():], links)
                elif link and not link.group(1).startswith("`"):
                    title = inline(link.group(1), links)
                    summary = _summary(text[link.end():], links)
                else:
                    # A leading declaration link is shown separately, so the title is the text after it.
                    rest = text[link.end():].lstrip(" :;,.—–-") if link else text
                    rest = rest[:1].upper() + rest[1:]
                    title = inline(_END.sub("", _first_sentence(rest or text)), links)
                out.append({"title": title, "summary": summary, "group": group, "link": _item_link(text, links)})
    # Headings only stand for results when a section has no list entries under them.
    has_entries = {entry["group"] for entry in out if not entry.get("heading")}
    return [
        {k: v for k, v in entry.items() if k != "heading"}
        for entry in out
        if not entry.get("heading") or entry["title"] not in has_entries
    ]
