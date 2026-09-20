// Policy 1: Always permit surfacing direct contradictions, regardless of confidence.
// Contradictions are the core feature — a low-confidence contradiction is
// still useful signal, so we never suppress these.
permit (
    principal == Service::"Detector",
    action == Action::"surface_finding",
    resource
)
when {
    resource.type == "direct_contradiction"
};

// Policy 2: Only permit surfacing circular-reasoning findings when confidence
// is high enough (>= 0.6). Weak circularity claims are noisy and hurt trust,
// so we're more conservative here than with direct contradictions.
permit (
    principal == Service::"Detector",
    action == Action::"surface_finding",
    resource
)
when {
    resource.type == "circular" &&
    resource.confidence >= 0.6
};