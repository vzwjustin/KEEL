from __future__ import annotations

from datetime import datetime
from typing import Optional

from keel.core.artifacts import load_yaml
from keel.core.paths import KeelPaths
from keel.models import (
    AlignmentArtifact,
    ConfidenceLevel,
    DriftArtifact,
    GoalArtifact,
    PlanArtifact,
    RecoveryArtifact,
    RecoveryIssue,
    RecoveryMode,
    RecoveryStep,
    SessionState,
    ValidationArtifact,
)
from keel.session import SessionService


MODE_RULES = {
    "rewind-plan-only": {
        "codes": {"KEE-DRF-005", "KEE-DRF-009", "KEE-DRF-014", "KEE-DRF-019", "KEE-DRF-021"},
        "confidence": ConfidenceLevel.INFERRED_HIGH,
        "summary": "Resynchronize the active plan, phase, and current brief before coding further.",
    },
    "update-goal-spec": {
        "codes": {"KEE-DRF-007", "KEE-DRF-008", "KEE-DRF-012"},
        "confidence": ConfidenceLevel.INFERRED_MEDIUM,
        "summary": "Current implementation no longer matches the original intent closely enough, so the goal or spec likely needs to be updated.",
    },
    "create-delta-and-continue": {
        "codes": {"KEE-DRF-003", "KEE-DRF-010", "KEE-DRF-011", "KEE-DRF-016"},
        "confidence": ConfidenceLevel.INFERRED_HIGH,
        "summary": "Behavior or contract change appears intentional enough that formalizing a delta is safer than pretending nothing changed.",
    },
    "rollback-code-path": {
        "codes": {"KEE-DRF-008", "KEE-DRF-018"},
        "confidence": ConfidenceLevel.INFERRED_MEDIUM,
        "summary": "The safest route may be to back out or isolate the off-course code path first, then realign the plan.",
    },
}


def _latest_checkpoint(paths: KeelPaths) -> Optional[str]:
    payload = load_yaml(paths.checkpoints_file)
    checkpoints = payload.get("checkpoints", [])
    if not checkpoints:
        return None
    return checkpoints[-1].get("created_at")


def _recovery_modes(drift: DriftArtifact) -> list[RecoveryMode]:
    present_codes = {finding.code for finding in drift.findings}
    modes = []
    for mode_id, rule in MODE_RULES.items():
        matched = sorted(present_codes & rule["codes"])
        if not matched:
            continue
        modes.append(
            RecoveryMode(
                mode_id=mode_id,
                label=mode_id.replace("-", " "),
                summary=rule["summary"],
                confidence=rule["confidence"],
                matched_codes=matched,
            )
        )
    if not modes:
        modes.append(
            RecoveryMode(
                mode_id="rewind-plan-only",
                label="rewind plan only",
                summary="No stronger recovery path was obvious, so the safest move is to re-anchor the plan and brief before further changes.",
                confidence=ConfidenceLevel.INFERRED_MEDIUM,
                matched_codes=[finding.code for finding in drift.findings[:3]],
            )
        )
    return modes


def _recommended_mode(modes: list[RecoveryMode]) -> RecoveryMode:
    preferred_order = [
        "create-delta-and-continue",
        "rewind-plan-only",
        "update-goal-spec",
        "rollback-code-path",
    ]
    for mode_id in preferred_order:
        for mode in modes:
            if mode.mode_id == mode_id:
                return mode
    return modes[0]


def _divergence_anchor(paths: KeelPaths, drift: DriftArtifact) -> tuple[str, str]:
    if drift.clusters:
        cluster = sorted(drift.clusters, key=lambda item: item.first_seen_at)[0]
        return (
            cluster.first_seen_at,
            f"Repeated drift started clustering around {cluster.layer} with codes {', '.join(cluster.related_codes[:3])}.",
        )
    checkpoint = _latest_checkpoint(paths)
    if checkpoint:
        return checkpoint, "The latest checkpoint is the last explicit aligned anchor before the current divergence."
    return drift.created_at.isoformat(), "No checkpoint or cluster anchor was available, so the current drift run is the first reliable divergence marker."


def _issues(drift: DriftArtifact, validation: Optional[ValidationArtifact]) -> list[RecoveryIssue]:
    rows: list[RecoveryIssue] = []
    for finding in drift.findings[:6]:
        rows.append(
            RecoveryIssue(
                issue_id=finding.code,
                kind="drift",
                summary=finding.summary,
                detail=finding.detail,
                severity=finding.severity,
                confidence=finding.confidence,
                evidence=finding.evidence[:6],
            )
        )
    if validation:
        for finding in validation.findings[:4]:
            rows.append(
                RecoveryIssue(
                    issue_id=finding.code,
                    kind="validation",
                    summary=finding.message,
                    detail=finding.suggested_action,
                    severity=finding.severity,
                    confidence=finding.confidence,
                    evidence=finding.paths[:4],
                )
            )
    return rows


def _candidate_paths(drift: DriftArtifact) -> list[str]:
    paths = []
    for finding in drift.findings:
        for evidence in finding.evidence:
            if "/" in evidence or evidence.endswith((".py", ".md", ".yaml", ".yml", ".toml", ".json")):
                if evidence not in paths:
                    paths.append(evidence)
    return paths[:8]


def _steps(
    *,
    paths: KeelPaths,
    goal: Optional[GoalArtifact],
    alignment: Optional[AlignmentArtifact],
    drift: DriftArtifact,
    mode: RecoveryMode,
) -> list[RecoveryStep]:
    candidate_paths = _candidate_paths(drift)
    steps = [
        RecoveryStep(
            step_id="REC-001",
            title="Replay the intended work",
            detail="Compare the active goal, current plan, and latest drift findings before changing more code.",
            paths=[str(paths.current_file), str(paths.current_brief_file), str(paths.goals_dir), str(paths.plans_dir)],
        ),
        RecoveryStep(
            step_id="REC-002",
            title=f"Apply recovery mode: {mode.label}",
            detail=mode.summary,
            paths=candidate_paths or [str(paths.plans_dir), str(paths.deltas_dir)],
        ),
        RecoveryStep(
            step_id="REC-003",
            title="Reconcile durable artifacts",
            detail="Update the matching plan, goal, spec, or delta artifacts so KEEL stops seeing the repo and the intent as different stories.",
            paths=[str(paths.goals_dir), str(paths.plans_dir), str(paths.deltas_dir), str(paths.unresolved_questions_file)],
        ),
        RecoveryStep(
            step_id="REC-004",
            title="Prove the recovery worked",
            detail="Re-run validate, drift, and done after the reconciliation so the next session resumes from aligned state.",
            paths=[str(paths.reports_dir / "validation"), str(paths.reports_dir / "drift")],
        ),
    ]
    if goal and goal.out_of_scope:
        steps[0].detail += f" Keep these invariants stable unless you intentionally change them: {', '.join(goal.out_of_scope[:2])}."
    if alignment and alignment.recommended_focus_area:
        steps[2].detail += f" Current recommended focus remains: {alignment.recommended_focus_area}."
    return steps


def build_recovery(
    *,
    paths: KeelPaths,
    session: SessionState,
    goal: Optional[GoalArtifact],
    plan: Optional[PlanArtifact],
    alignment: Optional[AlignmentArtifact],
    drift: DriftArtifact,
    validation: Optional[ValidationArtifact],
) -> RecoveryArtifact:
    # Freeze the current state as a checkpoint before recovery begins
    SessionService(paths).add_checkpoint(
        f"recovery: drift detected with {len(drift.findings)} findings",
        session,
        kind="recovery-anchor",
    )

    modes = _recovery_modes(drift)
    recommended = _recommended_mode(modes)
    divergence_at, divergence_reason = _divergence_anchor(paths, drift)
    issues = _issues(drift, validation)
    steps = _steps(paths=paths, goal=goal, alignment=alignment, drift=drift, mode=recommended)

    session.current_next_step = steps[0].title
    SessionService(paths).save(session)
    SessionService(paths).write_current_brief(
        goal=goal,
        plan=plan,
        baseline=None,
        alignment=alignment,
        research=None,
        unresolved_questions=[],
        decisions=SessionService(paths).load_decisions() + [f"Recovery mode selected: {recommended.label}"],
        blockers=[issue.issue_id for issue in issues if issue.severity.value in {"warning", "error", "blocker"}][:4],
        must_not_change=(goal.out_of_scope[:2] + goal.constraints[:2]) if goal else [],
    )

    return RecoveryArtifact(
        artifact_id=f"recovery-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=".",
        divergence_at=divergence_at,
        divergence_reason=divergence_reason,
        intent_replay={
            "goal": goal.goal_statement if goal else "not set",
            "phase": session.active_phase_id or "not set",
            "step": session.active_step_id or "not set",
            "next_step": session.current_next_step or "not set",
        },
        issues=issues,
        recovery_modes=modes,
        recommended_mode=recommended.mode_id,
        recovery_confidence=recommended.confidence,
        steps=steps,
        brief_path=str(paths.current_brief_file),
    )
