"""
MindMap Debugger — extraction layer (Groq + Strands version, Build It track).

Sends raw text (essay or transcript) to Groq's API (via Strands' Agent),
gets back structured propositions + relations, validates the shape, returns it.

Requirements:
  1. Get a free API key: https://console.groq.com  (no card needed)
  2. Set it as an environment variable:
     Windows (PowerShell):  $env:GROQ_API_KEY = "your-key-here"
  3. pip install groq strands-agents

Run directly:
    python extract.py
"""

import json
import os
import re

from strands import Agent
from strands.models.openai import OpenAIModel

MODEL_NAME = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are a reasoning analyst. Given a piece of text — either a written
argument/essay or a conversation/debate transcript — extract the distinct
claims being made and the logical relationships between them.

Rules:
- Break the text into atomic propositions (one claim per item, not whole sentences bundled together)
- If input is a transcript, tag each proposition with its speaker
- IMPORTANT: after listing propositions, explicitly check EVERY pair of
  propositions against each other for conflict — not just ones that are
  stated close together or in an obvious "but/however" sentence. Two claims
  can contradict even when nothing in the wording signals it directly.
  Example: "we need maximum speed with everything in memory" and "we need
  zero data loss if the system crashes" are a real contradiction even
  though neither sentence mentions the other.
- Only mark a relation as "contradicts" if BOTH propositions genuinely
  cannot be true/hold at the same time. Ask yourself: "if I accept A, am I
  logically forced to reject B?" If the answer is no, it is NOT a
  contradiction.
- Tension, trade-offs, difficulty, or one claim explaining why another is
  hard to achieve are NOT contradictions. "We are under time pressure" and
  "we need more time" is a real-world tension, not a logical contradiction
  — both can be simultaneously true statements about the situation.
- Only mark "depends_on" if removing the source proposition would make the
  target unsupported. Only mark "supports" if the source directly argues
  for or evidences the target.
- CRITICAL — circular reasoning detection: after you have listed all
  depends_on and supports relations, trace each chain. If A depends_on B
  (or A supports B), check whether B — directly, or through any other
  propositions — comes back to A. If a chain closes into a loop, you MUST
  emit EVERY edge in that loop, not just some of them. A cycle is only
  detectable downstream if all its edges are present; a single missing
  edge hides the entire loop.

  Worked example of a correctly emitted cycle:
    P1 depends_on P3, P3 depends_on P5, P5 depends_on P1
    → emit ALL THREE relations. Emitting only two makes the loop invisible.

  Second example (mixed relation types forming a cycle):
    P1 supports P2, P2 depends_on P3, P3 supports P1
    → emit all three. Cycles often alternate between supports and
      depends_on — a loop is a loop regardless of edge type.

  Do not invent a cycle. But if the chain genuinely closes, you MUST
  include every edge, or the pipeline will miss it entirely.
- Do not skip the pairwise check even if it feels like extra work — a
  missed implicit contradiction or a missed loop edge is a worse error
  than a few relations that turn out not to matter. But do not invent a
  contradiction or cycle just to have found one — an unnecessary false
  "contradicts" relation is just as much an error as a missed one.
- Assign a confidence score (0-1) to every relation — be conservative, not
  generous. If you are not at least 0.6 confident a "contradicts" relation
  is real, do not include it at all.

Example of a correctly caught implicit contradiction:

Input: "We'll use an in-memory cache for speed. The system must not lose data on crash."

Correct output:
{
  "propositions": [
    {"id": "P1", "text": "We will use an in-memory cache for speed", "speaker": null, "type": "claim"},
    {"id": "P2", "text": "The system must not lose data on crash", "speaker": null, "type": "premise"}
  ],
  "relations": [
    {"from": "P1", "to": "P2", "type": "contradicts", "confidence": 0.85}
  ]
}

Note: P1 and P2 don't share any words, but in-memory storage is lost on
crash, which directly conflicts with "must not lose data on crash." This
is exactly the kind of implicit contradiction to catch.

Example of something that is NOT a contradiction (do not flag this):

Input: "Our testing isn't complete yet. We should launch the product now
because the market window is closing."

This is NOT a contradiction. Both claims can be true at once — testing
being incomplete is a reason launching now is risky, but it does not make
"we should launch now" logically false. This is a real-world trade-off
between two pressures, not two claims that can't both hold. Correct
output for this pair: no "contradicts" relation (optionally a
"depends_on" or "supports" relation if one claim is offered as a reason
for/against the other).

Return ONLY valid JSON matching this schema, no prose, no markdown fences, no explanation:

{
  "propositions": [
    {"id": "P1", "text": "short restatement of the claim", "speaker": null, "type": "claim"}
  ],
  "relations": [
    {"from": "P1", "to": "P2", "type": "contradicts", "confidence": 0.85}
  ]
}

type for propositions is one of: claim, premise, conclusion
type for relations is one of: contradicts, depends_on, supports
speaker is null for essays, a name/label string for transcripts
"""


def _extract_json(raw_text: str) -> dict:
    text = raw_text.strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def _validate(data: dict) -> dict:
    assert "propositions" in data and "relations" in data, "missing top-level keys"

    prop_ids = set()
    for p in data["propositions"]:
        assert p.get("id") and p.get("text"), f"malformed proposition: {p}"
        assert p.get("type") in ("claim", "premise", "conclusion"), f"bad type: {p}"
        prop_ids.add(p["id"])

    for r in data["relations"]:
        assert r.get("from") in prop_ids, f"relation references unknown id: {r}"
        assert r.get("to") in prop_ids, f"relation references unknown id: {r}"
        assert r.get("type") in ("contradicts", "depends_on", "supports"), f"bad relation type: {r}"
        assert 0.0 <= r.get("confidence", -1) <= 1.0, f"bad confidence: {r}"

    return data


def extract(text: str, model: str = MODEL_NAME) -> dict:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable is not set. "
            "Get a free key at console.groq.com, then set it:\n"
            '  Windows (PowerShell):  $env:GROQ_API_KEY = "your-key-here"'
        )

    strands_model = OpenAIModel(
        client_args={
            "api_key": api_key,
            "base_url": "https://api.groq.com/openai/v1",
        },
        model_id=model,
        params={
            "temperature": 0,
            "max_tokens": 16000,
            "extra_body": {
                "reasoning_format": "hidden",
                "reasoning_effort": "medium",
            },
        },
    )

    agent = Agent(
        model=strands_model,
        system_prompt=SYSTEM_PROMPT,
    )

    try:
        result = agent(text)
        raw_text = str(result)
    except Exception as e:
        print("\n--- RAW ERROR DETAILS ---")
        print(repr(e))
        if hasattr(e, "response"):
            print("Response body:", e.response.text if hasattr(e.response, "text") else e.response)
        if hasattr(e, "body"):
            print("Error body:", e.body)
        print("--- END RAW ERROR DETAILS ---\n")
        raise

    try:
        data = _extract_json(raw_text)
    except (json.JSONDecodeError, AttributeError) as e:
        print("\n--- JSON PARSE FAILURE (raw model output below) ---")
        print(raw_text)
        print("--- END RAW MODEL OUTPUT ---\n")
        raise RuntimeError(f"Model output was not valid JSON: {e}") from e

    return _validate(data)


def _similarity(text_a: str, text_b: str) -> float:
    """
    Jaccard word-set similarity (intersection / union) between two
    proposition texts. Catches genuine paraphrases across runs without
    collapsing distinct claims that merely share common English words
    (the/is/because/their) — which the previous overlap/min metric did.
    """
    words_a = set(text_a.lower().rstrip(".").split())
    words_b = set(text_b.lower().rstrip(".").split())
    if not words_a or not words_b:
        return 0.0
    overlap = len(words_a & words_b)
    union = len(words_a | words_b)
    return overlap / union


def extract_consensus(text: str, model: str = MODEL_NAME, n_calls: int = 3) -> dict:
    """
    Runs extract() multiple times and merges results by proposition TEXT
    (ids are not stable across runs). Union of contradictions (max-confidence
    wins, floor of 0.5) plus union of depends_on/supports edges so that
    circular chains found by even one run survive the merge.

    Consensus safety: reverse-direction depends_on pairs across runs are
    collapsed to the higher-confidence direction, so we never fabricate a
    cycle that no single run ever saw.
    """
    all_props = {}
    all_rels = {}

    successful_runs = 0
    for i in range(n_calls):
        try:
            result = extract(text, model=model)
        except Exception as e:
            print(f"  Run {i+1}/{n_calls} failed: {e}")
            continue
        successful_runs += 1

        local_id_to_text = {}
        for p in result["propositions"]:
            raw_text = p["text"].strip()

            matched_key = None
            for existing_key in all_props:
                if _similarity(raw_text, existing_key) >= 0.6:
                    matched_key = existing_key
                    break

            if matched_key:
                local_id_to_text[p["id"]] = matched_key
            else:
                norm_text = raw_text.lower().rstrip(".")
                local_id_to_text[p["id"]] = norm_text
                all_props[norm_text] = {
                    "id": f"P{len(all_props) + 1}",
                    "text": raw_text,
                    "speaker": p.get("speaker"),
                    "type": p.get("type", "claim"),
                }

        for r in result["relations"]:
            from_text = local_id_to_text.get(r["from"])
            to_text = local_id_to_text.get(r["to"])
            if not from_text or not to_text:
                continue
            if r["type"] == "contradicts" and r["confidence"] < 0.5:
                continue
            key = (from_text, to_text, r["type"])
            if key not in all_rels or r["confidence"] > all_rels[key]["confidence"]:
                all_rels[key] = {"confidence": r["confidence"], "type": r["type"]}

    if successful_runs == 0:
        raise RuntimeError("All extraction runs failed — check Groq API status/key.")

    # Consensus safety: if two different runs disagree on the DIRECTION of
    # a depends_on relation (run A says X depends_on Y, run B says Y
    # depends_on X), keep only the higher-confidence direction. Otherwise
    # the merged graph contains both arrows and downstream cycle detection
    # reports a fabricated 2-node loop that no single run ever saw.
    #
    # We only do this for depends_on. Real bidirectional supports edges
    # CAN be circular ("A supports B and B supports A" is circular by
    # definition), so we leave supports alone.
    def _drop_one(key_a, key_b):
        a = all_rels.get(key_a)
        b = all_rels.get(key_b)
        if a is None or b is None:
            return
        if b["confidence"] > a["confidence"]:
            all_rels.pop(key_a, None)
        else:
            all_rels.pop(key_b, None)

    processed = set()
    for (from_t, to_t, rel_type) in list(all_rels.keys()):
        if rel_type != "depends_on":
            continue
        if (from_t, to_t, rel_type) in processed:
            continue
        reverse = (to_t, from_t, rel_type)
        if reverse in all_rels:
            _drop_one((from_t, to_t, rel_type), reverse)
        processed.add((from_t, to_t, rel_type))
        processed.add(reverse)

    merged_relations = []
    for (from_text, to_text, rel_type), rel in all_rels.items():
        merged_relations.append({
            "from": all_props[from_text]["id"],
            "to": all_props[to_text]["id"],
            "type": rel_type,
            "confidence": rel["confidence"],
        })

    merged = {
        "propositions": list(all_props.values()),
        "relations": merged_relations,
    }

    print(f"  Consensus from {successful_runs}/{n_calls} successful runs: "
          f"{len(merged['propositions'])} unique propositions, "
          f"{len(merged['relations'])} unique relations")

    return _validate(merged)


if __name__ == "__main__":
    sample = {
        "propositions": [
            {"id": "P1", "text": "We should use SQLite for speed", "speaker": "Agent_Arch", "type": "claim"},
            {"id": "P2", "text": "The system must survive process restarts", "speaker": "Agent_Sec", "type": "premise"},
        ],
        "relations": [
            {"from": "P1", "to": "P2", "type": "contradicts", "confidence": 0.8},
        ],
    }
    validated = _validate(sample)
    print("Validator OK (no API call needed for this check):")
    print(json.dumps(validated, indent=2))

    print("\nTrying a real extraction via Groq (through Strands)...")
    try:
        result = extract(
            "SQLite is fast enough for our needs. But the system must survive "
            "process restarts, and in-memory data does not survive restarts."
        )
        print("Extraction OK:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}")