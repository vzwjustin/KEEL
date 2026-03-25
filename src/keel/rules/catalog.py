ERROR_CODES = {
    "KEE-SCN-001": "Scan could not identify a likely runtime entrypoint.",
    "KEE-BAS-001": "Baseline was requested without an available scan artifact.",
    "KEE-GOL-001": "Goal artifact is missing a usable goal statement.",
    "KEE-QST-001": "Question generation found no grounded inputs to work from.",
    "KEE-ALN-001": "Alignment confidence is low because high-priority decisions remain unresolved.",
    "KEE-PLN-001": "Planner could not determine a concrete next step.",
    "KEE-VAL-001": "Active goal is missing success criteria.",
    "KEE-VAL-002": "No active plan exists for the current goal.",
    "KEE-VAL-003": "A behavior-changing goal has no linked delta artifact.",
    "KEE-DRF-001": "Repository files changed after the last scan or checkpoint without reconciliation.",
    "KEE-DNE-001": "Done gate failed because validation or drift blockers remain.",
}

CONFIDENCE_EXPLANATIONS = {
    "deterministic": "Backed directly by local file or git evidence.",
    "inferred-high-confidence": "Strongly suggested by multiple repo signals, but not directly proven.",
    "inferred-medium-confidence": "Plausible from partial evidence and should be verified before acting.",
    "heuristic-low-confidence": "A weak pattern match that should not be treated as settled fact.",
    "unresolved": "KEEL cannot honestly answer this yet from current local evidence.",
}
