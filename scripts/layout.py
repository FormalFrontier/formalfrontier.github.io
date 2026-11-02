"""Layered drawing of the dependency graph.

Foundations (no Formal Frontier dependencies) sit in the top row; each other
deliverable sits one row below its furthest dependency. Pinned revisions can
make the current graph cyclic, so a few edges are set aside before layering and
drawn upwards. Long edges pass through dummy points, a barycenter sweep orders
each row to reduce crossings, and nodes then move towards their neighbours.
"""

from __future__ import annotations

CHAR_WIDTH = 6.9  # average label width per character at the site's node font size
NODE_PAD = 20
LINE_HEIGHT = 15
NODE_PAD_Y = 12
NODE_GAP = 16
DUMMY_WIDTH = 6
ROW_GAP = 56
WRAP = 14


def label_lines(name: str) -> list[str]:
    """Split a long hyphenated name into two lines near its middle."""
    if len(name) <= WRAP or "-" not in name:
        return [name]
    cuts = [i for i, ch in enumerate(name) if ch == "-"]
    cut = min(cuts, key=lambda i: abs(i + 1 - len(name) / 2))
    return [name[: cut + 1], name[cut + 1:]]


def _isotonic(targets: list[float], gaps: list[float]) -> list[float]:
    """Closest positions to targets, in order, with at least gaps[i] between i and i+1."""
    offsets = [0.0]
    for g in gaps:
        offsets.append(offsets[-1] + g)
    values = [t - o for t, o in zip(targets, offsets)]
    blocks: list[list[float]] = []  # [sum, count]
    for v in values:
        blocks.append([v, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, c = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += c
    fitted = []
    for s, c in blocks:
        fitted.extend([s / c] * c)
    return [f + o for f, o in zip(fitted, offsets)]


def _break_cycles(deps: dict[str, list[str]]) -> set[tuple[str, str]]:
    """Edges whose removal leaves the graph acyclic (DFS back edges)."""
    back = set()
    state: dict[str, int] = {}

    def visit(node: str) -> None:
        state[node] = 1
        for dep in sorted(deps[node]):
            if state.get(dep) == 1:
                back.add((node, dep))
            elif dep not in state:
                visit(dep)
        state[node] = 2

    # Start from the nodes with the most dependents so cycles break at leaves.
    dependents = {n: 0 for n in deps}
    for node in deps:
        for dep in deps[node]:
            dependents[dep] += 1
    for node in sorted(deps, key=lambda n: (dependents[n], n)):
        if node not in state:
            visit(node)
    return back


def layered(deps: dict[str, list[str]], weights: dict[str, int]) -> dict:
    nodes = sorted(deps)
    back = _break_cycles(deps)
    forward = {n: [d for d in deps[n] if (n, d) not in back] for n in nodes}
    for n, d in back:
        if n not in forward[d]:
            forward[d].append(n)

    layer: dict[str, int] = {}

    def depth(node: str) -> int:
        if node not in layer:
            layer[node] = 1 + max((depth(d) for d in forward[node]), default=-1)
        return layer[node]

    # Deliverables without any project dependency links share the bottom row.
    isolated = {n for n in nodes if not deps[n] and not any(n in deps[m] for m in nodes)}
    for node in nodes:
        if node not in isolated:
            depth(node)
    rows = max(layer.values(), default=-1) + 1
    for node in isolated:
        layer[node] = rows
    rows = max(layer.values(), default=-1) + 1

    # Chains of dummy points for edges spanning more than one row.
    order: list[list[str]] = [[] for _ in range(rows)]
    for node in sorted(nodes, key=lambda n: (-weights.get(n, 0), n)):
        order[layer[node]].append(node)
    chains: dict[tuple[str, str], list[str]] = {}
    links: list[tuple[str, str]] = []  # (upper, lower) between adjacent rows
    for node in nodes:
        for dep in forward[node]:
            upper, lower = dep, node
            span = layer[lower] - layer[upper]
            chain = [upper]
            for k in range(1, span):
                dummy = f"\x00{upper}>{lower}>{k}"
                order[layer[upper] + k].append(dummy)
                layer[dummy] = layer[upper] + k
                chain.append(dummy)
            chain.append(lower)
            chains[(upper, lower)] = chain
            links.extend(zip(chain, chain[1:]))

    above: dict[str, list[str]] = {}
    below: dict[str, list[str]] = {}
    for a, b in links:
        below.setdefault(a, []).append(b)
        above.setdefault(b, []).append(a)

    def crossings() -> int:
        total = 0
        for c in range(rows - 1):
            pos_l = {n: i for i, n in enumerate(order[c])}
            pos_r = {n: i for i, n in enumerate(order[c + 1])}
            pairs = [(pos_l[a], pos_r[b]) for a, b in links if a in pos_l and b in pos_r]
            for i in range(len(pairs)):
                for j in range(i + 1, len(pairs)):
                    if (pairs[i][0] - pairs[j][0]) * (pairs[i][1] - pairs[j][1]) < 0:
                        total += 1
        return total

    def sweep(c: int, neighbours: dict, ref: int) -> None:
        pos = {n: i for i, n in enumerate(order[ref])}
        current = {n: i for i, n in enumerate(order[c])}

        def key(n: str) -> float:
            ns = [pos[m] for m in neighbours.get(n, []) if m in pos]
            return sum(ns) / len(ns) if ns else current[n]

        order[c].sort(key=lambda n: (key(n), current[n]))

    best = [list(col) for col in order]
    best_score = crossings()
    for _ in range(24):
        for c in range(1, rows):
            sweep(c, above, c - 1)
        for c in range(rows - 2, -1, -1):
            sweep(c, below, c + 1)
        score = crossings()
        if score < best_score:
            best, best_score = [list(col) for col in order], score
    order = best

    def width(n: str) -> float:
        if n.startswith("\x00"):
            return DUMMY_WIDTH
        return round(max(len(line) for line in label_lines(n)) * CHAR_WIDTH + NODE_PAD)

    def height(n: str) -> float:
        return 0 if n.startswith("\x00") else len(label_lines(n)) * LINE_HEIGHT + NODE_PAD_Y

    row_height = max((height(n) for n in nodes), default=0)
    x: dict[str, float] = {}
    for row in order:
        cursor = 0.0
        for n in row:
            x[n] = cursor + width(n) / 2
            cursor += width(n) + NODE_GAP
    widest = max((x[row[-1]] + width(row[-1]) / 2 for row in order if row), default=0)
    for row in order:
        if row:
            shift = (widest - (x[row[-1]] + width(row[-1]) / 2)) / 2
            for n in row:
                x[n] += shift

    def place(r: int, neighbours: dict) -> None:
        row = order[r]
        if not row:
            return
        targets = []
        for n in row:
            ns = [x[m] for m in neighbours.get(n, [])]
            targets.append(sum(ns) / len(ns) if ns else x[n])
        gaps = [(width(a) + width(b)) / 2 + NODE_GAP for a, b in zip(row, row[1:])]
        for n, value in zip(row, _isotonic(targets, gaps)):
            x[n] = value

    both = {n: above.get(n, []) + below.get(n, []) for n in layer}
    for _ in range(12):
        for r in range(1, rows):
            place(r, above)
        for r in range(rows - 2, -1, -1):
            place(r, below)
    for _ in range(4):
        for r in range(rows):
            place(r, both)
    left = min(x[n] - width(n) / 2 for n in x)
    for n in x:
        x[n] -= left
    total_width = max((x[n] + width(n) / 2 for n in x), default=0)
    total_height = rows * row_height + max(rows - 1, 0) * ROW_GAP
    pos = {n: (x[n], layer[n] * (row_height + ROW_GAP) + row_height / 2) for n in x}

    out_nodes = [{
        "name": n,
        "row": layer[n],
        "x": round(pos[n][0], 1),
        "y": round(pos[n][1], 1),
        "w": width(n),
        "h": height(n),
        "lines": label_lines(n),
    } for n in nodes]
    edges = []
    for node in nodes:
        for dep in deps[node]:
            reversed_ = (node, dep) in back
            chain = chains[(node, dep) if reversed_ else (dep, node)]
            points = []
            for i, n in enumerate(chain):
                px, py = pos[n]
                if i == 0:
                    py += height(n) / 2
                elif i == len(chain) - 1:
                    py -= height(n) / 2
                points.append([round(px, 1), round(py, 1)])
            edges.append({"from": node, "to": dep, "points": points, "cycle": reversed_})
    return {
        "width": round(total_width, 1),
        "height": round(total_height, 1),
        "rows": rows,
        "nodes": out_nodes,
        "edges": edges,
        "crossings": best_score,
        "isolated": len(isolated),
    }
