"""
MindMap Debugger — test suite.

Runs the pipeline against a handful of different input shapes to find
weak spots before building the UI on top. Each case targets something
different: no contradiction at all, a transcript with speakers, subtle/
implicit contradiction, and a longer messy real-world-style argument.

Usage:
    python test_cases.py
"""

from pipeline import run


CASES = {
    "no_contradiction": """
        Regular exercise improves cardiovascular health. It also tends to
        improve mood through endorphin release. Most health guidelines
        recommend at least 150 minutes of moderate activity per week.
    """,

    "transcript_with_speakers": """
        Alex: We should cut the marketing budget by half this quarter.
        Priya: That doesn't make sense, we just said growth is our top priority.
        Alex: Right, growth is the priority, that's why we need to spend more
              on marketing, not less.
        Priya: So you're saying both cut it and increase it?
    """,

    "implicit_contradiction": """
        Our database must handle all data in memory for maximum speed.
        We also need the system to be fully recoverable after any crash,
        with zero data loss, at all times.
    """,

    "long_messy_argument": """
        Remote work is clearly better for productivity, employees focus more
        without office distractions. That said, our best quarter ever was
        Q3, right after we brought everyone back to the office full time.
        Some people argue hybrid is the answer, but honestly hybrid just
        gives you the downsides of both. Still, I think we should let
        individual teams decide what works for them, since a one-size-fits-
        all policy rarely works well in practice.
    """,

    "single_claim_no_relations": """
        The sky appears blue during the day due to Rayleigh scattering.
    """,
}


if __name__ == "__main__":
    for name, text in CASES.items():
        print("=" * 60)
        print(f"CASE: {name}")
        print("=" * 60)
        try:
            findings = run(text.strip())
            if not findings:
                print("  -> No findings (may be correct, or may be a miss - check manually)")
            else:
                for f in findings:
                    print(f'  [{f["type"]}] confidence={f["confidence"]} — {f["description"]}')
        except Exception as e:
            print(f"  ERROR: {e}")
        print()
