"""
MindMap Debugger — pipeline runner.

Wires extract.py, detect.py, and cedar_gate.py together: paste text in,
get ranked, policy-filtered findings out. This is the core loop working
end to end.

  extract.py -> detect.py -> cedar_gate.py -> UI

Usage:
    python pipeline.py
    (edit SAMPLE_TEXT below, or import run() and call it with your own text)
"""

from extract import extract_consensus
from detect import build_findings
from cedar_gate import apply_gate


def run(text: str) -> list[dict]:
    """
    Full pipeline: text -> Groq extraction -> contradiction/cycle detection
    -> Cedar policy gate -> sorted, filtered findings (contradictions first,
    per your priority; low-confidence circular findings filtered out).
    """
    print("Extracting propositions and relations via Groq...")
    extraction = extract_consensus(text)
    print(f"  Found {len(extraction['propositions'])} propositions, "
          f"{len(extraction['relations'])} relations")

    print("Running contradiction + cycle detection...")
    findings = build_findings(extraction)
    print(f"  {len(findings)} findings before policy gate")

    print("Applying Cedar policy gate...")
    gated_findings = apply_gate(findings)
    print(f"  {len(gated_findings)} findings after policy gate\n")

    return gated_findings


SAMPLE_TEXT = """
I think we should launch the product now because the market window is closing fast.
Waiting even one more month means competitors get there first.
At the same time, our testing isn't complete yet, and we've committed to never
shipping anything without full testing, no matter the market pressure.
Also, the whole reason we're rushing is that we promised investors a Q1 launch,
and that promise depends on the testing being done properly, which is exactly
what we don't have time for.
"""


if __name__ == "__main__":
    findings = run(SAMPLE_TEXT)

    if not findings:
        print("No contradictions or circular reasoning detected.")
    else:
        print("Findings (sorted, contradictions first):\n")
        for f in findings:
            print(f'  [{f["type"]}] confidence={f["confidence"]}')
            print(f'    {f["description"]}\n')