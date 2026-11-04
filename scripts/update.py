#!/usr/bin/env python3
"""Collect public data about the Formal Frontier deliverables and write site/data.

Everything comes from public GitHub: the organization's repository list and the
public Git history of each deliverable. A deliverable is a public, non-archived
repository whose default branch has a `formalization.yaml`. Its default branch is
its release history: every first-parent commit is one release.

Usage: scripts/update.py [--cache DIR] [--out DIR] [--offline]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402
import markdown  # noqa: E402

ORG = "FormalFrontier"
SITE_REPO = "formalfrontier.github.io"
ROOT = Path(__file__).resolve().parent.parent

THEOREM_RE = re.compile(
    r"^\s*(?:@\[[^\]]*\]\s*)?(?:(?:private|protected|noncomputable|nonrec|scoped)\s+)*"
    r"(?:theorem|lemma)\s+\S"
)
DEFINITION_RE = re.compile(
    r"^\s*(?:@\[[^\]]*\]\s*)?"
    r"(?:(?:private|protected|noncomputable|nonrec|scoped|partial|unsafe)\s+)*"
    r"(?:def|abbrev|structure|class|inductive|instance)\b"
)
def is_library_file(path: str) -> bool:
    """Whether a Lean file is library code rather than a test or an example."""
    for part in path.split("/")[:-1]:
        if part.lower() in ("test", "tests", "example", "examples"):
            return False
        if re.search(r"(?:Test|Tests|Example|Examples)$", part):
            return False
    return True


def git(repo: Path, *args: str, text: bool = True) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=text,
    ).stdout


def git_ok(repo: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    return result.stdout if result.returncode == 0 else None


def api(path: str) -> list | dict:
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "formalfrontier-dashboard",
        },
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def list_candidates() -> list[dict]:
    repos = []
    page = 1
    while True:
        batch = api(f"/orgs/{ORG}/repos?type=public&per_page=100&page={page}")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return sorted(
        (
            {"name": r["name"], "branch": r["default_branch"]}
            for r in repos
            if not r["archived"] and not r["fork"] and not r["private"] and r["name"] != SITE_REPO
        ),
        key=lambda r: r["name"],
    )


def sync(cache: Path, name: str, branch: str) -> Path:
    path = cache / f"{name}.git"
    url = f"https://github.com/{ORG}/{name}.git"
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--bare", "--quiet", url, str(path)], check=True
        )
    else:
        git(path, "fetch", "--quiet", "--prune", "--force", url,
            f"+refs/heads/{branch}:refs/heads/{branch}")
    return path


def read_file(repo: Path, rev: str, path: str) -> str | None:
    return git_ok(repo, "show", f"{rev}:{path}")


def day_of(timestamp: int) -> str:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).date().isoformat()


def release_history(repo: Path, rev: str) -> list[dict]:
    """One entry per release: commit, time and cumulative Lean statistics."""
    releases = []
    for line in git(repo, "log", "--first-parent", "--reverse", "--format=%H %ct", rev).splitlines():
        sha, ts = line.split()
        releases.append({"sha": sha, "time": int(ts), "lines": 0, "files": 0,
                         "theorems": 0, "definitions": 0})
    index = {r["sha"]: r for r in releases}

    # Line and declaration deltas per release, from the Lean diffs alone.
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--first-parent", "--reverse", "--no-renames",
         "-p", "--unified=0", "--format=\x01%H", rev, "--", "*.lean"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8", errors="replace")
    deltas: dict[str, list[int]] = {}
    current = None
    in_header = False
    library = True
    for line in out.split("\n"):
        if line.startswith("\x01"):
            current = deltas.setdefault(line[1:], [0, 0, 0, 0])
            in_header = False
            continue
        if line.startswith("diff --git "):
            in_header = True
            library = is_library_file(line.rsplit(" b/", 1)[-1])
            continue
        if in_header:
            if line.startswith("new file mode"):
                current[1] += 1
            elif line.startswith("deleted file mode"):
                current[1] -= 1
            elif line.startswith("@@"):
                in_header = False
            continue
        if not line or current is None or line[0] not in "+-":
            continue
        step = 1 if line[0] == "+" else -1
        current[0] += step
        if library:
            body = line[1:]
            if THEOREM_RE.match(body):
                current[2] += step
            elif DEFINITION_RE.match(body):
                current[3] += step
    totals = [0, 0, 0, 0]
    for release in releases:
        delta = deltas.get(release["sha"])
        if delta:
            totals = [a + b for a, b in zip(totals, delta)]
        release["lines"], release["files"], release["theorems"], release["definitions"] = totals
    return releases


def tree_counts(repo: Path, rev: str) -> dict:
    """Exact Lean statistics of the current release, to check the history."""
    files = [p for p in git(repo, "ls-tree", "-r", "--name-only", rev).splitlines()
             if p.endswith(".lean")]
    lines = theorems = definitions = 0
    if files:
        out = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "--batch"],
            input="".join(f"{rev}:{p}\n" for p in files).encode(),
            check=True, capture_output=True,
        ).stdout
        pos = 0
        for path in files:
            header_end = out.index(b"\n", pos)
            size = int(out[pos:header_end].split()[2])
            body = out[header_end + 1: header_end + 1 + size].decode("utf-8", errors="replace")
            pos = header_end + 1 + size + 1
            text_lines = body.split("\n")
            if text_lines and text_lines[-1] == "":
                text_lines.pop()
            lines += len(text_lines)
            if is_library_file(path):
                for text in text_lines:
                    if THEOREM_RE.match(text):
                        theorems += 1
                    elif DEFINITION_RE.match(text):
                        definitions += 1
    return {"files": len(files), "lines": lines, "theorems": theorems,
            "definitions": definitions}


def direct_dependencies(manifest_text: str | None) -> tuple[list[str], list[str]]:
    """Formal Frontier and other direct dependencies from lake-manifest.json."""
    if not manifest_text:
        return [], []
    manifest = json.loads(manifest_text)
    internal, external = [], []
    for package in manifest.get("packages", []):
        if package.get("inherited", False):
            continue
        url = package.get("url", "")
        match = re.match(rf"https://github\.com/{ORG}/([^/]+?)(?:\.git)?/?$", url)
        if match:
            internal.append(match.group(1))
        else:
            external.append(package.get("name", url))
    return sorted(internal), sorted(external)


def text(value) -> str:
    return " ".join(str(value).split()) if value else ""


def source_list(config: dict) -> list[dict]:
    sources = []
    for source in config.get("sources") or []:
        if not isinstance(source, dict):
            continue
        sources.append({
            "title": text(source.get("title")),
            "authors": [text(a) for a in source.get("authors") or []],
            "type": text(source.get("type")),
            "url": source.get("id") if str(source.get("id", "")).startswith("https://") else None,
            "relationship": text(source.get("relationship")),
        })
    return sources


def display_title(title: str, name: str) -> str:
    """The project name, or a readable form of the repository name.

    The repository name is used when the project name is a single identifier
    such as the repository slug, or a sentence rather than a name.
    """
    if " " in title and len(title) <= 48:
        return title
    words = name.replace("-", " ").replace("_", " ")
    return words[:1].upper() + words[1:]


def declaration_url(name: str, sha: str, path: str) -> str:
    return f"https://github.com/{ORG}/{name}/blob/{sha}/{path}"


def nominated_highlights(config: dict, name: str, sha: str,
                         links: markdown.Links) -> list[dict]:
    """The optional `highlights` field of formalization.yaml."""
    items = []
    for entry in config.get("highlights") or []:
        if not isinstance(entry, dict) or not entry.get("title"):
            continue
        declarations = []
        for decl in entry.get("declarations") or []:
            if isinstance(decl, dict) and decl.get("declaration") and decl.get("file"):
                declarations.append({
                    "name": text(decl["declaration"]),
                    "url": declaration_url(name, sha, str(decl["file"]).lstrip("/")),
                })
        items.append({
            "title": text(entry["title"]),
            "html": markdown.inline(text(entry.get("statement")), links),
            "declarations": declarations,
        })
    return items


def collect(cache: Path, offline: bool) -> list[dict]:
    if offline:
        candidates = [{"name": p.name[:-4], "branch": None}
                      for p in sorted(cache.glob("*.git"))]
    else:
        candidates = list_candidates()
    deliverables = []
    for candidate in candidates:
        name = candidate["name"]
        repo = cache / f"{name}.git" if offline else sync(cache, name, candidate["branch"])
        branch = candidate["branch"] or git(repo, "symbolic-ref", "--short", "HEAD").strip()
        rev = f"refs/heads/{branch}"
        config_text = read_file(repo, rev, "formalization.yaml")
        if config_text is None:
            continue
        config = yaml.safe_load(config_text) or {}
        sha = git(repo, "rev-parse", rev).strip()
        releases = release_history(repo, rev)
        exact = tree_counts(repo, rev)
        last = releases[-1]
        for key in ("lines", "files", "theorems", "definitions"):
            if last[key] != exact[key]:
                print(f"warning: {name}: history {key} {last[key]} != tree {exact[key]}",
                      file=sys.stderr)
        deps, external = direct_dependencies(read_file(repo, rev, "lake-manifest.json"))
        toolchain = (read_file(repo, rev, "lean-toolchain") or "").strip()
        project = config.get("project") or {}
        status = config.get("status") or {}
        dirs = {"/".join(path.split("/")[:k])
                for path in git(repo, "ls-tree", "-r", "--name-only", rev).splitlines()
                for k in range(1, path.count("/") + 1)}
        links = markdown.Links(ORG, name, sha, "", dirs)
        readme = read_file(repo, rev, "README.md") or ""
        headline = markdown.section(readme, "Headline results")
        main_results = []
        for result in status.get("main_results") or []:
            if isinstance(result, dict) and result.get("declaration") and result.get("file"):
                main_results.append({
                    "name": text(result["declaration"]),
                    "url": declaration_url(name, sha, str(result["file"]).lstrip("/")),
                })
        classification = config.get("classification") or {}
        deliverables.append({
            "name": name,
            "title": display_title(text(project.get("name")), name),
            "description": text(project.get("description")),
            "url": f"https://github.com/{ORG}/{name}",
            "sha": sha,
            "toolchain": toolchain.split(":")[-1] if toolchain else "",
            "license": text(project.get("license")),
            "sources": source_list(config),
            "arxiv": [text(c) for c in classification.get("arxiv") or []],
            "msc2020": [text(c) for c in classification.get("msc2020") or []],
            "deps": deps,
            "external_deps": external,
            "main_results": main_results,
            "releases": releases,
            "stats": exact,
            "highlights": nominated_highlights(config, name, sha, links),
            "headline": markdown.render(headline, links) if headline else "",
            "headline_items": markdown.items(headline, links) if headline else [],
        })
    names = {d["name"] for d in deliverables}
    for d in deliverables:
        d["deps"] = [x for x in d["deps"] if x in names]
    return deliverables


def daily_history(deliverables: list[dict], today: dt.date) -> dict:
    events = []
    for d in deliverables:
        for release in d["releases"]:
            events.append((release["time"], d["name"], release))
    events.sort(key=lambda e: e[0])
    if not events:
        return {"days": []}
    start = dt.date.fromisoformat(day_of(events[0][0]))
    state: dict[str, dict] = {}
    series = defaultdict(list)
    i = 0
    day = start
    while day <= today:
        released_today = 0
        while i < len(events) and day_of(events[i][0]) <= day.isoformat():
            _, name, release = events[i]
            state[name] = release
            released_today += 1
            i += 1
        series["days"].append(day.isoformat())
        series["deliverables"].append(len(state))
        series["lines"].append(sum(r["lines"] for r in state.values()))
        series["theorems"].append(sum(r["theorems"] for r in state.values()))
        series["definitions"].append(sum(r["definitions"] for r in state.values()))
        series["releases"].append(released_today)
        day += dt.timedelta(days=1)
    return dict(series)


def per_repo_series(d: dict) -> list[list]:
    """Daily change points [day, lines] of one deliverable, for sparklines."""
    points: dict[str, int] = {}
    for release in d["releases"]:
        points[day_of(release["time"])] = release["lines"]
    return [[day, lines] for day, lines in sorted(points.items())]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache" / "repos")
    parser.add_argument("--out", type=Path, default=ROOT / "site" / "data")
    parser.add_argument("--offline", action="store_true",
                        help="use the cached clones without contacting GitHub")
    args = parser.parse_args()

    deliverables = collect(args.cache, args.offline)
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    history = daily_history(deliverables, today)

    dependents = defaultdict(list)
    for d in deliverables:
        for dep in d["deps"]:
            dependents[dep].append(d["name"])

    graph = layout.layered(
        {d["name"]: d["deps"] for d in deliverables},
        {d["name"]: d["stats"]["lines"] for d in deliverables},
    )

    rows = []
    for d in deliverables:
        first, last = d["releases"][0], d["releases"][-1]
        rows.append({
            "name": d["name"],
            "title": d["title"],
            "description": d["description"],
            "url": d["url"],
            "sha": d["sha"],
            "toolchain": d["toolchain"],
            "license": d["license"],
            "sources": d["sources"],
            "arxiv": d["arxiv"],
            "msc2020": d["msc2020"],
            "deps": d["deps"],
            "dependents": sorted(dependents[d["name"]]),
            "external_deps": d["external_deps"],
            "main_results": len(d["main_results"]),
            "first_release": day_of(first["time"]),
            "last_release": day_of(last["time"]),
            "releases": len(d["releases"]),
            **d["stats"],
            "series": per_repo_series(d),
        })

    sources = {}
    for d in deliverables:
        for s in d["sources"]:
            if s["type"] != "software" and s["title"]:
                sources[(s["title"], tuple(s["authors"]))] = s
    totals = {
        "deliverables": len(rows),
        "lines": sum(r["lines"] for r in rows),
        "files": sum(r["files"] for r in rows),
        "theorems": sum(r["theorems"] for r in rows),
        "definitions": sum(r["definitions"] for r in rows),
        "releases": sum(r["releases"] for r in rows),
        "dependencies": sum(len(r["deps"]) for r in rows),
        "sources": len(sources),
    }

    out = args.out
    write_json(out / "dashboard.json", {
        "generated": today.isoformat(),
        "updated": now.strftime("%Y-%m-%dT%H:%MZ"),
        "totals": totals,
        "history": history,
        "deliverables": rows,
        "graph": graph,
    })
    write_json(out / "highlights.json", {
        "generated": today.isoformat(),
        "updated": now.strftime("%Y-%m-%dT%H:%MZ"),
        "deliverables": [{
            "name": d["name"],
            "title": d["title"],
            "description": d["description"],
            "url": d["url"],
            "sources": [s for s in d["sources"] if s["type"] != "software"],
            "highlights": d["highlights"],
            "items": d["headline_items"],
        } for d in deliverables],
    })
    headlines = out / "headlines"
    headlines.mkdir(parents=True, exist_ok=True)
    keep = set()
    for d in deliverables:
        if d["headline"]:
            target = headlines / f"{d['name']}.html"
            target.write_text(d["headline"])
            keep.add(target.name)
    for stale in headlines.glob("*.html"):
        if stale.name not in keep:
            stale.unlink()
    print(f"{totals['deliverables']} deliverables, {totals['lines']} Lean lines, "
          f"{totals['theorems']} theorems, {totals['releases']} releases")


if __name__ == "__main__":
    main()
