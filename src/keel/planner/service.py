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
    paths: list[str] = []
    if not scan:
        return paths
    for item in scan.entrypoints[:2] + scan.modules[:3] + scan.configs[:2]:
        for path in item.paths:
            if path not in paths:
                paths.append(path)
    return paths[:6]


# ---------------------------------------------------------------------------
# Phase 1 helpers — Lock Reality
# ---------------------------------------------------------------------------

def _build_phase1_steps(
    scan: Optional[ScanArtifact],
    baseline: Optional[BaselineArtifact],
    questions: Optional[QuestionArtifact],
    related_paths: list[str],
) -> list[PlanStep]:
    steps: list[PlanStep] = []
    step_counter = 1
    unknowns = baseline.unknowns if baseline else []
    top_questions = [q.question for q in (questions.questions if questions else [])[:3]]

    # --- Per-unknown resolution steps (max 3) ---
    if unknowns:
        for unknown in unknowns[:3]:
            steps.append(PlanStep(
                step_id=f"PH1-STEP{step_counter}",
                title=f"Resolve: {unknown.title}",
                detail=f"Investigate and resolve this unknown before it blocks planning. {unknown.detail}",
                related_paths=unknown.paths[:4] if unknown.paths else related_paths,
                assumptions_to_verify=[unknown.title],
                done_definition=f"'{unknown.title}' is either confirmed, refuted, or explicitly deferred with rationale.",
            ))
            step_counter += 1
    else:
        # Fallback: generic source-of-truth confirmation
        steps.append(PlanStep(
            step_id=f"PH1-STEP{step_counter}",
            title="Confirm the current source of truth",
            detail="Verify the most likely entrypoint, authoritative config, and module boundary before making behavior assumptions.",
            related_paths=related_paths,
            assumptions_to_verify=[],
            done_definition="The active runtime path and authoritative files are explicit enough to guide the next phase.",
        ))
        step_counter += 1

    # --- Multiple entrypoints step ---
    if scan and len(scan.entrypoints) > 1:
        ep_names = [ep.name for ep in scan.entrypoints]
        ep_paths: list[str] = []
        for ep in scan.entrypoints:
            ep_paths.extend(ep.paths)
        steps.append(PlanStep(
            step_id=f"PH1-STEP{step_counter}",
            title="Determine the primary entrypoint",
            detail=f"Multiple entrypoints detected: {', '.join(ep_names)}. Identify which is the active runtime entry.",
            related_paths=ep_paths[:6],
            assumptions_to_verify=[f"Is '{ep}' the primary entrypoint?" for ep in ep_names[:3]],
            done_definition="One entrypoint is identified as primary, or the relationship between entrypoints is documented.",
        ))
        step_counter += 1

    # --- No tests detected ---
    if scan and not scan.tests:
        steps.append(PlanStep(
            step_id=f"PH1-STEP{step_counter}",
            title="Identify existing test coverage",
            detail="No test files were detected during scan. Determine if tests exist elsewhere or if coverage is truly absent.",
            related_paths=related_paths,
            assumptions_to_verify=["Does the repo have any test infrastructure?"],
            done_definition="Test coverage status is known: either tests are located or their absence is confirmed.",
        ))
        step_counter += 1

    # --- Open questions step (always present if there are questions) ---
    if top_questions:
        steps.append(PlanStep(
            step_id=f"PH1-STEP{step_counter}",
            title="Resolve the highest-value open questions",
            detail="Answer the questions that unblock planning or expose hidden drift risk.",
            related_paths=[],
            assumptions_to_verify=top_questions,
            done_definition="High-priority unknowns are either resolved or consciously deferred with a reason.",
        ))
        step_counter += 1

    return steps


# ---------------------------------------------------------------------------
# Phase 2 helpers — Shape the Change / Map Reality
# ---------------------------------------------------------------------------

def _build_phase2(
    goal: Optional[GoalArtifact],
    scan: Optional[ScanArtifact],
    goal_mode: GoalMode,
    related_paths: list[str],
) -> tuple[str, str, list[PlanStep]]:
    """Returns (phase_title, phase_objective, steps)."""

    scope_paths = goal.scope if goal and goal.scope else related_paths
    success_criteria = goal.success_criteria if goal else []
    scope_desc = ", ".join(scope_paths[:4]) if scope_paths else "repo root"

    if goal_mode in {GoalMode.UNDERSTAND, GoalMode.VERIFY_CLAIMS}:
        title = "Map Reality"
        objective = "Document how the current implementation behaves without changing it."
        steps: list[PlanStep] = []

        # Trace specific entrypoints from scan
        if scan and scan.entrypoints:
            ep_names = [ep.name for ep in scan.entrypoints[:3]]
            ep_paths: list[str] = []
            for ep in scan.entrypoints[:3]:
                ep_paths.extend(ep.paths)
            steps.append(PlanStep(
                step_id="PH2-STEP1",
                title=f"Trace runtime path from: {', '.join(ep_names)}",
                detail=f"Follow the runtime or build path starting from the detected entrypoints ({', '.join(ep_names)}) and capture evidence.",
                related_paths=ep_paths[:6] if ep_paths else related_paths,
                assumptions_to_verify=[],
                done_definition="The current behavior path is summarized with evidence from actual entrypoints.",
            ))
        else:
            steps.append(PlanStep(
                step_id="PH2-STEP1",
                title="Trace the real current path",
                detail="Follow the likely runtime or build path and capture the evidence that matters for future work.",
                related_paths=related_paths,
                assumptions_to_verify=[],
                done_definition="The current behavior path is summarized with evidence and clear uncertainty notes.",
            ))

        if goal_mode == GoalMode.VERIFY_CLAIMS and success_criteria:
            steps.append(PlanStep(
                step_id="PH2-STEP2",
                title="Check each claim against repo evidence",
                detail=f"Verify the following claims: {'; '.join(success_criteria[:3])}",
                related_paths=list(scope_paths[:6]),
                assumptions_to_verify=list(success_criteria[:3]),
                done_definition="Each claim is marked verified, refuted, or inconclusive with evidence.",
            ))

        return title, objective, steps

    elif goal_mode in {GoalMode.FIX, GoalMode.WIRE_UP_INCOMPLETE, GoalMode.DEBUG}:
        title = "Shape The Change"
        objective = "Locate and scope the fix within the identified files."
        steps = [
            PlanStep(
                step_id="PH2-STEP1",
                title=f"Isolate the issue in: {scope_desc}",
                detail=f"Examine the specific files in scope ({scope_desc}) to locate the root cause or incomplete wiring.",
                related_paths=list(scope_paths[:6]),
                assumptions_to_verify=list(success_criteria[:3]),
                done_definition="The root cause or gap is identified with a concrete fix strategy.",
            ),
        ]
        return title, objective, steps

    elif goal_mode in {GoalMode.ADD_FEATURE, GoalMode.EXTEND, GoalMode.SHIP_MVP}:
        title = "Shape The Change"
        objective = "Translate the active goal into a bounded change with validation and delta coverage."
        steps = [
            PlanStep(
                step_id="PH2-STEP1",
                title="Write delta before implementation",
                detail="Capture what will change, what acceptance looks like, and validation mapping before any code is written.",
                related_paths=list(scope_paths[:6]),
                assumptions_to_verify=[],
                done_definition="A delta artifact exists describing the intended change and its boundaries.",
            ),
            PlanStep(
                step_id="PH2-STEP2",
                title="Define acceptance criteria from success_criteria",
                detail=f"Turn goal success criteria into verifiable checks: {'; '.join(success_criteria[:3]) if success_criteria else 'define from goal statement'}.",
                related_paths=[],
                assumptions_to_verify=list(success_criteria[:3]),
                done_definition="Each success criterion has a matching validation check or test.",
            ),
        ]
        return title, objective, steps

    elif goal_mode == GoalMode.REFACTOR:
        title = "Shape The Change"
        objective = "Document current contracts before restructuring."
        steps = [
            PlanStep(
                step_id="PH2-STEP1",
                title="Document current behavior contracts before refactoring",
                detail=f"Record the public surface, return types, side effects, and invariants of code in: {scope_desc}.",
                related_paths=list(scope_paths[:6]),
                assumptions_to_verify=[],
                done_definition="Pre-refactor behavior contracts are captured and can be verified after the change.",
            ),
        ]
        return title, objective, steps

    elif goal_mode == GoalMode.HARDEN:
        title = "Shape The Change"
        objective = "Identify gaps in test coverage and harden the codebase."
        # Build module-specific testing steps
        modules = scan.modules if scan else []
        module_names = [m.name for m in modules[:4]]
        module_paths: list[str] = []
        for m in modules[:4]:
            module_paths.extend(m.paths)

        detail = "Focus test coverage on the following modules"
        if module_names:
            detail += f": {', '.join(module_names)}"
        else:
            detail += f" within: {scope_desc}"

        steps = [
            PlanStep(
                step_id="PH2-STEP1",
                title="Map test coverage for detected modules",
                detail=f"{detail}. Identify untested paths and edge cases.",
                related_paths=module_paths[:6] if module_paths else list(scope_paths[:6]),
                assumptions_to_verify=[],
                done_definition="A coverage map exists showing which modules/functions lack tests.",
            ),
        ]
        return title, objective, steps

    else:
        # CLEAN_UP_DRIFT or any future mode — generic shape
        title = "Shape The Change"
        objective = "Translate the active goal into a bounded change with validation and delta coverage."
        steps = [
            PlanStep(
                step_id="PH2-STEP1",
                title="Define the bounded change",
                detail=f"Write or update the delta, acceptance criteria, and validation mapping for changes in: {scope_desc}.",
                related_paths=list(scope_paths[:6]),
                assumptions_to_verify=list(success_criteria[:3]),
                done_definition="The intended change is captured with clear acceptance and validation links.",
            ),
        ]
        return title, objective, steps


# ---------------------------------------------------------------------------
# Phase 3 helpers — Execute
# ---------------------------------------------------------------------------

def _build_phase3_steps(
    goal: Optional[GoalArtifact],
    related_paths: list[str],
) -> list[PlanStep]:
    steps: list[PlanStep] = []
    scope_paths = goal.scope if goal and goal.scope else related_paths
    success_criteria = goal.success_criteria if goal else []
    scope_desc = ", ".join(scope_paths[:4]) if scope_paths else "repo root"

    # --- Per-criterion execution steps (max 3) ---
    if success_criteria:
        for i, criterion in enumerate(success_criteria[:3], start=1):
            steps.append(PlanStep(
                step_id=f"PH3-STEP{i}",
                title=f"Implement: {criterion[:80]}",
                detail=f"Execute the smallest change that satisfies this criterion. Keep changes within: {scope_desc}.",
                related_paths=list(scope_paths[:6]),
                assumptions_to_verify=[],
                done_definition=f"Criterion met: {criterion}",
            ))
        step_next = len(steps) + 1
    else:
        steps.append(PlanStep(
            step_id="PH3-STEP1",
            title="Execute the current slice",
            detail=f"Change the smallest practical set of files that advances the active goal. Keep changes within: {scope_desc}.",
            related_paths=list(scope_paths[:6]),
            assumptions_to_verify=[],
            done_definition="The planned code or documentation slice is implemented and locally reviewed.",
        ))
        step_next = 2

    # --- Validate step ---
    steps.append(PlanStep(
        step_id=f"PH3-STEP{step_next}",
        title="Validate and reconcile",
        detail="Run tests or alternate validation, then update the brief, worklog, and drift signals.",
        related_paths=list(scope_paths[:6]),
        assumptions_to_verify=[],
        done_definition="Validation signals are recorded and the session state matches repo reality.",
    ))

    return steps


# ---------------------------------------------------------------------------
# Phase 4 helpers — Reconcile
# ---------------------------------------------------------------------------

def _build_phase4_steps(
    goal: Optional[GoalArtifact],
    alignment: Optional[AlignmentArtifact],
) -> list[PlanStep]:
    steps: list[PlanStep] = []
    step_counter = 1
    constraints = goal.constraints if goal else []
    mismatches = alignment.mismatches if alignment else []

    constraint_note = ""
    if constraints:
        constraint_note = f" Constraints to verify: {'; '.join(constraints[:3])}."

    steps.append(PlanStep(
        step_id=f"PH4-STEP{step_counter}",
        title="Run anti-drift gates",
        detail=f"Use validate, trace, drift, and done checks to make sure the slice did not silently diverge.{constraint_note}",
        related_paths=[],
        assumptions_to_verify=[],
        done_definition="No unacknowledged blocker remains in validation or drift outputs.",
    ))
    step_counter += 1

    # --- Per-mismatch verification steps ---
    if mismatches:
        for mismatch in mismatches[:3]:
            steps.append(PlanStep(
                step_id=f"PH4-STEP{step_counter}",
                title=f"Verify resolved: {mismatch.summary[:70]}",
                detail=f"Confirm this alignment mismatch is addressed: {mismatch.detail}",
                related_paths=[],
                assumptions_to_verify=[mismatch.summary],
                done_definition=f"Mismatch '{mismatch.summary}' is verified resolved or explicitly deferred.",
            ))
            step_counter += 1

    return steps


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

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

    # Phase 1 — Lock Reality
    phase1_steps = _build_phase1_steps(scan, baseline, questions, related_paths)

    # Phase 2 — Shape the Change / Map Reality
    phase2_title, phase2_objective, phase2_steps = _build_phase2(
        goal, scan, goal_mode, related_paths,
    )

    # Phase 3 — Execute
    phase3_steps = _build_phase3_steps(goal, related_paths)

    # Phase 4 — Reconcile
    phase4_steps = _build_phase4_steps(goal, alignment)

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
            done_definition=phase2_steps[0].done_definition if phase2_steps else "Phase complete.",
            steps=phase2_steps,
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
