"""
MindMap Debugger — detection layer.

Takes the {"propositions": [...], "relations": [...]} output from extract.py
and produces a sorted list of "findings" — things worth showing the user,
ranked by what you asked for: contradictions first, cycles second.

  extract.py -> detect.py -> cedar gate -> UI
                ^^^^^^^^^^ this file

Run directly for a smoke test:
    python detect.py
"""

from collections import defaultdict

def _dedupe_cycles(cycles: list[list[str]]) -> list[list[str]]:
    """
    Collapses cycles that visit the same set of nodes into a single entry.
    DFS can rediscover the same underlying cycle more than once — e.g. once
    starting the walk from node A, once from node B — producing two entries
    that are really the same loop, just written starting/rotated
    differently, or (in degenerate cases) literally identical. We treat two
    cycles as the same if their node sets match, keeping only the first
    occurrence.
    """
    seen_node_sets = set()
    deduped = []
    for cycle in cycles:
        # cycle is like [A, B, C, A] — drop the repeated closing node
        # before comparing, since only the set of distinct nodes matters
        node_set = frozenset(cycle[:-1])
        if node_set in seen_node_sets:
            continue
        seen_node_sets.add(node_set)
        deduped.append(cycle)
    return deduped

def find_cycles(propositions: list[dict], relations: list[dict]) -> list[list[str]]:
    """
    DFS cycle detection over depends_on and supports edges — both describe
    a directed reasoning link, and circular reasoning in real arguments
    often alternates between them (e.g. "A depends on B" + "B supports A"
    is exactly the same circular structure as two depends_on edges, just
    phrased differently by the model).
    """
    graph = defaultdict(list)
    for r in relations:
        if r["type"] in ("depends_on", "supports"):
            graph[r["from"]].append(r["to"])

    all_ids = [p["id"] for p in propositions]
    visited = set()
    in_stack = set()
    cycles = []

    def dfs(node, path):
        if node in in_stack:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        in_stack.add(node)
        for neighbor in graph[node]:
            dfs(neighbor, path + [node])
        in_stack.discard(node)

    for pid in all_ids:
        if pid not in visited:
            dfs(pid, [])

    return _dedupe_cycles(cycles)


def build_findings(extraction: dict) -> list[dict]:
    """
    Turn raw propositions/relations into a sorted list of findings.
    Each finding has: type, confidence, involved proposition ids, and a
    plain-language description — this is what the Cedar gate evaluates
    and what the UI ultimately displays.
    """
    propositions = extraction["propositions"]
    relations = extraction["relations"]
    prop_lookup = {p["id"]: p for p in propositions}

    findings = []

    # 1. Direct contradictions — highest priority, no graph walk needed.
    # Dedupe by unordered pair: "A contradicts B" and "B contradicts A" are
    # the same finding, and the model sometimes emits both directions.
    seen_pairs = set()
    for r in relations:
        if r["type"] == "contradicts":
            pair_key = frozenset([r["from"], r["to"]])
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            a, b = prop_lookup[r["from"]], prop_lookup[r["to"]]
            findings.append({
                "type": "direct_contradiction",
                "confidence": r["confidence"],
                "involves": [r["from"], r["to"]],
                "claims": [a["text"], b["text"]],
                "description": f'"{a["text"]}" conflicts with "{b["text"]}"',
            })

    # 2. Circular reasoning — second priority
    cycles = find_cycles(propositions, relations)
    for cycle in cycles:
        texts = [prop_lookup[pid]["text"] for pid in cycle]
        # cycle confidence = average of the edge confidences forming it (simple heuristic)
        edge_confs = []
        for i in range(len(cycle) - 1):
            for r in relations:
                if (r["from"] == cycle[i] and r["to"] == cycle[i + 1]
                        and r["type"] in ("depends_on", "supports")):
                    edge_confs.append(r["confidence"])
        avg_conf = sum(edge_confs) / len(edge_confs) if edge_confs else 0.5
        findings.append({
            "type": "circular",
            "confidence": round(avg_conf, 2),
            "involves": cycle,
            "claims": texts,
            "description": " → ".join(texts) + " (circular)",
        })

    # Sort: contradictions before cycles, higher confidence first within each type
    priority = {"direct_contradiction": 0, "circular": 1}
    findings.sort(key=lambda f: (priority[f["type"]], -f["confidence"]))

    return findings


if __name__ == "__main__":
    # smoke test with hand-built extraction output
    sample_extraction = {
        "propositions": [
            {"id": "P1", "text": "In-memory SQLite is fast enough", "speaker": "Arch", "type": "claim"},
            {"id": "P2", "text": "System must survive restarts", "speaker": "Sec", "type": "premise"},
            {"id": "P3", "text": "In-memory data does not survive restarts", "speaker": "Sec", "type": "claim"},
            {"id": "P4", "text": "P4 depends on P1 being true", "speaker": "Coder", "type": "claim"},
        ],
        "relations": [
            {"from": "P1", "to": "P3", "type": "contradicts", "confidence": 0.9},
            {"from": "P1", "to": "P4", "type": "depends_on", "confidence": 0.7},
            {"from": "P4", "to": "P1", "type": "depends_on", "confidence": 0.6},  # circular on purpose
        ],
    }

    findings = build_findings(sample_extraction)
    print(f"Found {len(findings)} findings (sorted, contradictions first):\n")
    for f in findings:
        print(f'  [{f["type"]}] confidence={f["confidence"]} — {f["description"]}')