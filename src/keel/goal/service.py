from __future__ import annotations

from datetime import datetime
from typing import Optional

from keel.models import GoalArtifact, GoalMode


def build_goal(
    *,
    repo_root: str,
    mode: GoalMode,
    goal_statement: Optional[str],
    scope: Optional[list[str]],
    out_of_scope: Optional[list[str]],
    constraints: Optional[list[str]],
    success_criteria: Optional[list[str]],
    risks: Optional[list[str]],
    assumptions: Optional[list[str]],
    unresolved_questions: Optional[list[str]],
) -> GoalArtifact:
    statement = goal_statement or {
        GoalMode.UNDERSTAND: "Understand what really exists in this repository and where to start safely.",
        GoalMode.DEBUG: "Find the real failing path and reduce uncertainty before changing behavior.",
        GoalMode.FIX: "Fix the targeted behavior without introducing undocumented drift.",
        GoalMode.WIRE_UP_INCOMPLETE: "Wire up the incomplete or partial implementation safely.",
        GoalMode.EXTEND: "Extend the existing implementation while preserving alignment.",
        GoalMode.REFACTOR: "Refactor the implementation without changing behavior.",
        GoalMode.HARDEN: "Strengthen reliability and guardrails around the existing implementation.",
        GoalMode.ADD_FEATURE: "Add a feature without drifting from the current repo reality.",
        GoalMode.SHIP_MVP: "Ship a practical MVP with clear scope and anti-drift guardrails.",
        GoalMode.CLEAN_UP_DRIFT: "Bring the active repo state back into alignment with its intent.",
        GoalMode.VERIFY_CLAIMS: "Verify implementation claims against the actual repository evidence.",
    }[mode]
    return GoalArtifact(
        artifact_id=f"goal-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=repo_root,
        mode=mode,
        goal_statement=statement,
        scope=scope or [],
        out_of_scope=out_of_scope or [],
        constraints=constraints or [],
        success_criteria=success_criteria or [],
        risks=risks or [],
        assumptions=assumptions or [],
        unresolved_questions=unresolved_questions or [],
    )
