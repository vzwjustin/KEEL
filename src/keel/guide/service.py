from __future__ import annotations

from typing import Optional

from keel.core.paths import KeelPaths
from keel.models import (
    DriftArtifact,
    GoalArtifact,
    GoalMode,
    PlanArtifact,
    PlanPhase,
    PlanStep,
    ScanArtifact,
    SessionState,
    ValidationArtifact,
)


# ---------------------------------------------------------------------------
# Phase-aware coaching tips
# ---------------------------------------------------------------------------

_PHASE_TIPS: dict[str, dict[str, list[str]]] = {
    "Lock Reality": {
        "what_to_do": [
            "Read the scan and baseline artifacts to understand what the repo contains today.",
            "Verify every assumption listed in the step before moving forward.",
            "If anything looks stale or ambiguous, run `keel scan` again.",
        ],
        "what_to_avoid": [
            "Do not start writing code yet -- this phase is about understanding, not changing.",
            "Do not skip unresolved questions; they will cause drift later.",
        ],
    },
    "Shape the Change": {
        "what_to_do": [
            "Define the smallest vertical slice that satisfies the goal.",
            "Make sure every file you plan to touch is listed in related_paths.",
            "Record a delta artifact before any implementation begins.",
        ],
        "what_to_avoid": [
            "Avoid broad scaffolding -- prefer a single finished slice.",
            "Do not ignore alignment mismatches; resolve them now or note them as accepted risk.",
        ],
    },
    "Execute": {
        "what_to_do": [
            "Implement the change described in the current step.",
            "Run local tests and validation after each meaningful edit.",
            "Keep edits within the scope declared in the goal artifact.",
        ],
        "what_to_avoid": [
            "Do not wander into unrelated files or refactors outside the current step scope.",
            "Do not skip `keel check` after finishing the implementation.",
        ],
    },
    "Reconcile": {
        "what_to_do": [
            "Run `keel check` to confirm validation and drift are clear.",
            "Review the trace artifact to make sure every goal criterion maps to evidence.",
            "If drift warnings remain, address them or record an explicit decision.",
        ],
        "what_to_avoid": [
            "Do not mark the step done if drift warnings are still active and unacknowledged.",
        ],
    },
}

# ---------------------------------------------------------------------------
# Mode-aware coaching nudges
# ---------------------------------------------------------------------------

_MODE_NUDGES: dict[GoalMode, str] = {
    GoalMode.UNDERSTAND: "Focus on reading and documenting -- resist the urge to fix things.",
    GoalMode.DEBUG: "Reproduce the issue first, then isolate the root cause before patching.",
    GoalMode.FIX: "Keep the fix minimal; record a delta for every behavioral change.",
    GoalMode.WIRE_UP_INCOMPLETE: "Trace the incomplete wiring path end-to-end before connecting anything.",
    GoalMode.EXTEND: "Verify the existing contract is satisfied before extending it.",
    GoalMode.REFACTOR: "Behavior must not change -- run validation before and after every edit.",
    GoalMode.HARDEN: "Add tests and guards around the weakest paths identified in the baseline.",
    GoalMode.ADD_FEATURE: "Build the feature in a single vertical slice; avoid partial scaffolding.",
    GoalMode.SHIP_MVP: "Prioritize the shortest path to a working end-to-end flow.",
    GoalMode.CLEAN_UP_DRIFT: "Resolve the highest-severity drift findings first.",
    GoalMode.VERIFY_CLAIMS: "Cross-reference implementation claims against actual repo evidence.",
}


def _find_active_step(plan: PlanArtifact, session: SessionState) -> tuple[Optional[PlanPhase], Optional[PlanStep]]:
    """Return the active (phase, step) pair based on session state or plan default."""
    active_phase_id = session.active_phase_id
    active_step_id = session.active_step_id

    for phase in plan.phases:
        if active_phase_id and phase.phase_id != active_phase_id:
            continue
        for step in phase.steps:
            if active_step_id and step.step_id != active_step_id:
                continue
            return phase, step
        # If we matched the phase but not a specific step, return the first pending step.
        for step in phase.steps:
            if step.status == "pending":
                return phase, step

    # Fallback: return the plan's first phase/step.
    if plan.phases and plan.phases[0].steps:
        return plan.phases[0], plan.phases[0].steps[0]
    return None, None


def _build_context(
    scan: Optional[ScanArtifact],
    goal: Optional[GoalArtifact],
) -> dict[str, object]:
    context: dict[str, object] = {}
    if scan:
        context["languages"] = [item.name for item in scan.languages]
        context["entrypoints"] = [item.name for item in scan.entrypoints[:6]]
        context["build_systems"] = [item.name for item in scan.build_systems]
    if goal:
        context["goal_mode"] = goal.mode.value
        context["goal_statement"] = goal.goal_statement
        context["scope"] = goal.scope[:6]
        context["constraints"] = goal.constraints[:4]
        context["out_of_scope"] = goal.out_of_scope[:4]
    return context


def _build_warnings(
    drift: Optional[DriftArtifact],
    validation: Optional[ValidationArtifact],
    session: SessionState,
) -> list[str]:
    warnings: list[str] = []
    if drift and drift.findings:
        for finding in drift.findings[:3]:
            warnings.append(f"[drift] {finding.summary}")
    if validation and validation.findings:
        for finding in validation.findings[:3]:
            warnings.append(f"[validation] {finding.message}")
    if session.drift_warnings:
        existing_codes = {w.split("]")[0] for w in warnings}
        for code in session.drift_warnings[:3]:
            tag = f"[session-drift] {code}"
            if tag not in existing_codes:
                warnings.append(tag)
    return warnings


def _suggested_commands(
    phase: Optional[PlanPhase],
    drift: Optional[DriftArtifact],
    validation: Optional[ValidationArtifact],
    goal: Optional[GoalArtifact],
    session: SessionState,
) -> list[str]:
    commands: list[str] = []

    # If no goal exists yet, the first thing to do is start.
    if not goal:
        return ["keel start", "keel scan"]

    has_drift = drift and drift.findings
    has_validation_issues = validation and validation.findings

    if has_drift or has_validation_issues:
        commands.append("keel check")
    if has_drift:
        commands.append("keel drift --mode=auto")

    phase_title = phase.title if phase else ""
    if phase_title == "Lock Reality":
        commands.extend(["keel scan", "keel baseline", "keel questions"])
    elif phase_title in ("Shape the Change",):
        commands.extend(["keel align", "keel plan"])
    elif phase_title == "Execute":
        commands.extend(["keel check", "keel delta"])
    elif phase_title == "Reconcile":
        commands.extend(["keel check", "keel trace", "keel done"])

    if session.unresolved_question_ids:
        commands.append("keel questions")

    commands.append("keel status")

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for cmd in commands:
        if cmd not in seen:
            seen.add(cmd)
            unique.append(cmd)
    return unique


def build_guidance(
    paths: KeelPaths,
    session: SessionState,
    goal: Optional[GoalArtifact] = None,
    plan: Optional[PlanArtifact] = None,
    scan: Optional[ScanArtifact] = None,
    drift: Optional[DriftArtifact] = None,
    validation: Optional[ValidationArtifact] = None,
) -> dict[str, object]:
    """Build contextual development guidance for the current step."""

    # --- No goal yet: early return with bootstrap guidance ---
    if not goal:
        return {
            "current_step": "No active goal. Run `keel start` to begin.",
            "what_to_do": [
                "Run `keel start` to scan the repo, define a goal, and generate a plan.",
                "If you already have a scan, run `keel goal` to set the goal manually.",
            ],
            "what_to_avoid": [
                "Do not start making changes without an active goal and plan.",
            ],
            "done_when": "A goal and plan are active in the session.",
            "context": _build_context(scan, goal),
            "warnings": _build_warnings(drift, validation, session),
            "suggested_commands": ["keel start", "keel scan"],
        }

    # --- No plan yet ---
    if not plan:
        return {
            "current_step": f"Goal is set ({goal.mode.value}) but no plan exists yet.",
            "what_to_do": [
                "Run `keel plan` to generate a structured plan from the current goal.",
                "Review any unresolved questions before planning.",
            ],
            "what_to_avoid": [
                "Do not start implementation without a plan -- you will drift.",
            ],
            "done_when": "A plan artifact is generated and the first step is identified.",
            "context": _build_context(scan, goal),
            "warnings": _build_warnings(drift, validation, session),
            "suggested_commands": ["keel plan", "keel questions", "keel align"],
        }

    # --- Active plan: find the current step ---
    phase, step = _find_active_step(plan, session)

    if not phase or not step:
        return {
            "current_step": "Plan exists but no actionable step was found.",
            "what_to_do": [
                "Run `keel plan` to regenerate the plan.",
                "Check if all steps have been completed with `keel status`.",
            ],
            "what_to_avoid": [
                "Do not add steps manually; let the planner generate them.",
            ],
            "done_when": "An active step is identified or all steps are done.",
            "context": _build_context(scan, goal),
            "warnings": _build_warnings(drift, validation, session),
            "suggested_commands": ["keel plan", "keel status"],
        }

    # --- Build the full contextual guidance ---
    phase_title = phase.title
    phase_tips = _PHASE_TIPS.get(phase_title, _PHASE_TIPS["Execute"])

    # Start from phase-level tips, then enrich with step-specific detail.
    what_to_do = list(phase_tips["what_to_do"])

    # Add step-specific actions derived from the step itself.
    if step.detail:
        what_to_do.insert(0, step.detail)
    if step.assumptions_to_verify:
        what_to_do.append(
            f"Verify these assumptions first: {', '.join(step.assumptions_to_verify[:3])}"
        )
    if step.related_paths:
        what_to_do.append(
            f"Focus on these paths: {', '.join(step.related_paths[:4])}"
        )

    # Trim to a reasonable size.
    what_to_do = what_to_do[:5]

    what_to_avoid = list(phase_tips["what_to_avoid"])

    # Add mode-specific nudge.
    mode_nudge = _MODE_NUDGES.get(goal.mode)
    if mode_nudge:
        what_to_do.append(mode_nudge)

    # Unresolved questions warning.
    if goal.unresolved_questions:
        what_to_avoid.append(
            f"Do not ignore unresolved questions: {goal.unresolved_questions[0]}"
        )

    warnings = _build_warnings(drift, validation, session)
    if warnings:
        what_to_avoid.append("Address drift/validation warnings before advancing the step.")

    return {
        "current_step": f"[{phase_title}] {step.title}",
        "what_to_do": what_to_do,
        "what_to_avoid": what_to_avoid[:3],
        "done_when": step.done_definition,
        "context": _build_context(scan, goal),
        "warnings": warnings,
        "suggested_commands": _suggested_commands(phase, drift, validation, goal, session),
    }
