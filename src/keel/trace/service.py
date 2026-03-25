from __future__ import annotations

from datetime import datetime
from typing import Optional

from keel.models import GoalArtifact, PlanArtifact, TraceArtifact, TraceRow, ValidationArtifact


def build_trace(
    *,
    repo_root: str,
    goal: Optional[GoalArtifact],
    plan: Optional[PlanArtifact],
    validation: Optional[ValidationArtifact],
) -> TraceArtifact:
    rows: list[TraceRow] = []
    step_ids = []
    if plan:
        for phase in plan.phases:
            step_ids.extend(step.step_id for step in phase.steps)

    criteria = goal.success_criteria if goal and goal.success_criteria else ["No explicit success criteria recorded yet."]
    for index, criterion in enumerate(criteria, start=1):
        rows.append(
            TraceRow(
                row_id=f"TRC-{index:03d}",
                goal_reference=criterion,
                validation_reference=validation.status if validation else "validation-not-run",
                plan_step_ids=step_ids[:3],
                status="linked" if plan and validation else "partial",
            )
        )

    return TraceArtifact(
        artifact_id=f"trace-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=repo_root,
        rows=rows,
    )
