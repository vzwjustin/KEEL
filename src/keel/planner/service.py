from __future__ import annotations

from datetime import datetime
from typing import Optional

from keel.models import (
    AlignmentArtifact,
    BaselineArtifact,
    GoalArtifact,
    GoalMode,
    PlanArtifact,
    PlanPhase,
    PlanStep,
    QuestionArtifact,
    ScanArtifact,
)


def _related_paths(scan: Optional[ScanArtifact]) -> list[str]:
    paths = []
    if not scan:
        return paths
    for item in scan.entrypoints[:2] + scan.modules[:3] + scan.configs[:2]:
        for path in item.paths:
            if path not in paths:
                paths.append(path)
    return paths[:6]


def build_plan(
    *,
    repo_root: str,
    scan: Optional[ScanArtifact],
    baseline: Optional[BaselineArtifact],
    goal: Optional[GoalArtifact],
    alignment: Optional[AlignmentArtifact],
    questions: Optional[QuestionArtifact],
) -> PlanArtifact:
    goal_mode = goal.mode if goal else GoalMode.UNDERSTAND
    related_paths = _related_paths(scan)
    top_questions = [question.question for question in (questions.questions if questions else [])[:3]]
    unknowns = [item.title for item in (baseline.unknowns if baseline else [])[:3]]

    phase1_steps = [
        PlanStep(
            step_id="PH1-STEP1",
            title="Confirm the current source of truth",
            detail="Verify the most likely entrypoint, authoritative config, and module boundary before making behavior assumptions.",
            related_paths=related_paths,
            assumptions_to_verify=unknowns,
            done_definition="The active runtime path and authoritative files are explicit enough to guide the next phase.",
        ),
        PlanStep(
            step_id="PH1-STEP2",
            title="Resolve the highest-value open questions",
            detail="Answer the questions that unblock planning or expose hidden drift risk.",
            related_paths=[],
            assumptions_to_verify=top_questions,
            done_definition="High-priority unknowns are either resolved or consciously deferred with a reason.",
        ),
    ]

    if goal_mode in {GoalMode.UNDERSTAND, GoalMode.VERIFY_CLAIMS}:
        phase2_title = "Map Reality"
        phase2_objective = "Document how the current implementation behaves without changing it."
        phase2_step = PlanStep(
            step_id="PH2-STEP1",
            title="Trace the real current path",
            detail="Follow the likely runtime or build path and capture the evidence that matters for future work.",
            related_paths=related_paths,
            assumptions_to_verify=[],
            done_definition="The current behavior path is summarized with evidence and clear uncertainty notes.",
        )
    else:
        phase2_title = "Shape The Change"
        phase2_objective = "Translate the active goal into a bounded change with validation and delta coverage."
        phase2_step = PlanStep(
            step_id="PH2-STEP1",
            title="Define the bounded change",
            detail="Write or update the delta, acceptance criteria, and validation mapping before implementation grows.",
            related_paths=related_paths,
            assumptions_to_verify=goal.success_criteria if goal else [],
            done_definition="The intended change is captured with clear acceptance and validation links.",
        )

    phase3_steps = [
        PlanStep(
            step_id="PH3-STEP1",
            title="Execute the current slice",
            detail="Change the smallest practical set of files that advances the active goal while staying aligned with the plan.",
            related_paths=related_paths,
            assumptions_to_verify=[],
            done_definition="The planned code or documentation slice is implemented and locally reviewed.",
        ),
        PlanStep(
            step_id="PH3-STEP2",
            title="Validate and reconcile",
            detail="Run tests or alternate validation, then update the brief, worklog, and drift signals.",
            related_paths=related_paths,
            assumptions_to_verify=[],
            done_definition="Validation signals are recorded and the session state matches repo reality.",
        ),
    ]

    phase4_steps = [
        PlanStep(
            step_id="PH4-STEP1",
            title="Run anti-drift gates",
            detail="Use validate, trace, drift, and done checks to make sure the slice did not silently diverge.",
            related_paths=[],
            assumptions_to_verify=[],
            done_definition="No unacknowledged blocker remains in validation or drift outputs.",
        )
    ]

    phases = [
        PlanPhase(
            phase_id="PHASE-1",
            title="Lock Reality",
            objective="Reduce ambiguity in the current repo flatline before deeper action.",
            done_definition="Current-state facts are solid enough to drive the next move safely.",
            steps=phase1_steps,
        ),
        PlanPhase(
            phase_id="PHASE-2",
            title=phase2_title,
            objective=phase2_objective,
            done_definition=phase2_step.done_definition,
            steps=[phase2_step],
        ),
        PlanPhase(
            phase_id="PHASE-3",
            title="Execute",
            objective="Carry the active slice through implementation and local validation.",
            done_definition="The current change slice is implemented and locally validated.",
            steps=phase3_steps,
        ),
        PlanPhase(
            phase_id="PHASE-4",
            title="Reconcile",
            objective="Close the loop between goal, plan, validation, and actual repo state.",
            done_definition="Drift checks pass or every remaining issue is explicitly acknowledged.",
            steps=phase4_steps,
        ),
    ]

    focus = alignment.recommended_focus_area if alignment else "Start with the highest-confidence next step."
    current_next_step = phases[0].steps[0].title if phases and phases[0].steps else "No next step available"

    return PlanArtifact(
        artifact_id=f"plan-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=repo_root,
        focus_area=focus,
        phases=phases,
        current_next_step=current_next_step,
    )
