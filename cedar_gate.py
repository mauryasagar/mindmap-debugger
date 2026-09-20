"""
MindMap Debugger — Cedar policy gate.

Enforces the same rules defined in policies.cedar:
  - direct_contradiction findings: always surfaced (any confidence)
  - circular findings: only surfaced if confidence >= 0.6

This mirrors Cedar's policy logic in Python so it can run without the full
Cedar authorization engine, while staying true to the actual policy spec
in policies.cedar (see that file for the canonical rules).

  extract.py -> detect.py -> cedar_gate.py -> UI
                              ^^^^^^^^^^^^^ this file

Run directly for a smoke test:
    python cedar_gate.py
"""

CIRCULAR_CONFIDENCE_THRESHOLD = 0.6

PRINCIPAL = "Service::\"Detector\""


def is_permitted(finding: dict) -> bool:
    """
    Mirrors the Cedar policy decision for a single finding.
    Returns True if the finding should be surfaced to the user.
    """
    finding_type = finding.get("type")
    confidence = finding.get("confidence", 0.0)

    if finding_type == "direct_contradiction":
        # Policy 1: always permit, regardless of confidence
        return True

    if finding_type == "circular":
        # Policy 2: permit only if confidence >= threshold
        return confidence >= CIRCULAR_CONFIDENCE_THRESHOLD

    # Unknown finding type — deny by default (fail closed, not open)
    return False


def apply_gate(findings: list[dict]) -> list[dict]:
    """
    Takes the full findings list from detect.py's build_findings() and
    returns only the findings permitted by policy.
    """
    permitted = [f for f in findings if is_permitted(f)]
    return permitted


if __name__ == "__main__":
    sample_findings = [
        {"type": "direct_contradiction", "confidence": 0.9, "involves": ["P1", "P3"],
         "description": "\"In-memory SQLite is fast enough\" conflicts with \"In-memory data does not survive restarts\""},
        {"type": "direct_contradiction", "confidence": 0.3, "involves": ["P2", "P4"],
         "description": "low-confidence contradiction example"},
        {"type": "circular", "confidence": 0.75, "involves": ["P1", "P4"],
         "description": "P1 → P4 → P1 (circular)"},
        {"type": "circular", "confidence": 0.4, "involves": ["P5", "P6"],
         "description": "weak circular example — should be filtered out"},
    ]

    print(f"Principal: {PRINCIPAL}\n")
    print(f"Input findings: {len(sample_findings)}")
    for f in sample_findings:
        decision = "PERMIT" if is_permitted(f) else "DENY"
        print(f'  [{decision}] type={f["type"]} confidence={f["confidence"]} — {f["description"]}')

    gated = apply_gate(sample_findings)
    print(f"\nFindings surfaced after Cedar gate: {len(gated)} / {len(sample_findings)}")
    for f in gated:
        print(f'  ✓ [{f["type"]}] confidence={f["confidence"]} — {f["description"]}')