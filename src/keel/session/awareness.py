from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from keel.config import KeelConfig
from keel.core.artifacts import load_latest_model, load_model_by_artifact_id, save_artifact, save_yaml
from keel.core.paths import KeelPaths, now_iso
from keel.drift import detect_drift
from keel.models import (
    AlignmentArtifact,
    BaselineArtifact,
    DeltaArtifact,
    DriftArtifact,
    GoalArtifact,
    PlanArtifact,
    QuestionArtifact,
    ResearchArtifact,
    ScanArtifact,
    SessionState,
    TraceArtifact,
    ValidationArtifact,
)
from keel.trace import build_trace
from keel.validators import run_validation

from .alerts import update_alert_feed
from .service import SessionService


WATCH_IGNORED_DIRECTORIES = {".git", ".hg", ".svn", ".keel", "keel", ".pytest_cache", "__pycache__"}


def _preferred_model(directory: Path, artifact_id: Optional[str], model_type):
    if artifact_id:
        model = load_model_by_artifact_id(directory, artifact_id, model_type)
        if model is not None:
            return model
    return load_latest_model(directory, model_type)


def load_active_bundle(paths: KeelPaths, session: SessionState) -> dict[str, object | None]:
    research_id = session.research_artifact_ids[-1] if session.research_artifact_ids else None
    return {
        "scan": _preferred_model(paths.scans_dir, session.latest_scan_id, ScanArtifact),
        "baseline": _preferred_model(paths.baselines_dir, session.latest_baseline_id, BaselineArtifact),
        "goal": _preferred_model(paths.goals_dir, session.active_goal_id, GoalArtifact),
        "research": _preferred_model(paths.research_artifacts_dir, research_id, ResearchArtifact),
        "questions": load_latest_model(paths.questions_dir, QuestionArtifact),
        "alignment": _preferred_model(paths.alignments_dir, session.latest_alignment_id, AlignmentArtifact),
        "plan": _preferred_model(paths.plans_dir, session.active_plan_id, PlanArtifact),
        "validation": _preferred_model(paths.reports_dir / "validation", session.latest_validation_id, ValidationArtifact),
        "trace": _preferred_model(paths.reports_dir / "trace", session.latest_trace_id, TraceArtifact),
        "drift": _preferred_model(paths.reports_dir / "drift", session.latest_drift_id, DriftArtifact),
    }


def refresh_current_brief(
    paths: KeelPaths,
    session: SessionState,
    *,
    validation: Optional[ValidationArtifact] = None,
    drift: Optional[DriftArtifact] = None,
) -> Path:
    session_service = SessionService(paths)
    bundle = load_active_bundle(paths, session)
    validation = validation or bundle["validation"]
    drift = drift or bundle["drift"]
    blockers: list[str] = []
    if validation:
        blockers.extend(
            [
                finding.code
                for finding in validation.findings
                if finding.severity.value in {"error", "blocker"}
            ][:3]
        )
    if drift:
        blockers.extend(
            [
                finding.code
                for finding in drift.findings
                if finding.severity.value in {"warning", "error", "blocker"}
            ][:3]
        )
    goal = bundle["goal"]
    return session_service.write_current_brief(
        goal=goal,
        plan=bundle["plan"],
        baseline=bundle["baseline"],
        alignment=bundle["alignment"],
        research=bundle["research"],
        unresolved_questions=[item.get("question", "") for item in session_service.load_unresolved_questions()][:4],
        decisions=session_service.load_decisions(),
        blockers=blockers,
        must_not_change=(goal.out_of_scope[:2] + goal.constraints[:2]) if goal else [],
    )


def repo_watch_fingerprint(paths: KeelPaths, config: KeelConfig) -> str:
    ignored = set(config.ignored_directories) | WATCH_IGNORED_DIRECTORIES
    rows: list[str] = []
    for current_root, dirnames, filenames in os.walk(paths.root):
        dirnames[:] = sorted(name for name in dirnames if name not in ignored)
        for filename in sorted(filenames):
            if filename == ".DS_Store":
                continue
            path = Path(current_root) / filename
            try:
                stat = path.stat()
            except OSError:
                continue
            rel_path = path.relative_to(paths.root)
            rows.append(f"{rel_path}:{stat.st_mtime_ns}:{stat.st_size}")
    return hashlib.sha1("\n".join(rows).encode("utf-8")).hexdigest()


def latest_repo_change_at(paths: KeelPaths, config: KeelConfig) -> Optional[str]:
    ignored = set(config.ignored_directories) | WATCH_IGNORED_DIRECTORIES
    latest_timestamp: float | None = None
    for current_root, dirnames, filenames in os.walk(paths.root):
        dirnames[:] = sorted(name for name in dirnames if name not in ignored)
        for filename in filenames:
            if filename == ".DS_Store":
                continue
            path = Path(current_root) / filename
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            if latest_timestamp is None or modified > latest_timestamp:
                latest_timestamp = modified
    if latest_timestamp is None:
        return None
    return datetime.fromtimestamp(latest_timestamp).astimezone().isoformat()


def _write_drift_notification(
    paths: KeelPaths,
    drift: object,
    alerts: list[dict],
    *,
    replan_suggested: bool = False,
    replan_reason: str = "",
) -> None:
    """Write a one-shot notification file only when new drift codes appear (state transition)."""
    # No findings → reset state and stay silent.
    current_codes: list[str] = []
    if hasattr(drift, "findings") and drift.findings:
        current_codes = sorted({f.code for f in drift.findings})

    # Load the last-emitted code set for transition comparison.
    from keel.core.artifacts import load_yaml as _load_yaml
    prev_state = _load_yaml(paths.drift_notification_state_file) or {}
    prev_codes: list[str] = prev_state.get("codes", [])

    # Persist current state regardless (clears stale prev state when drift resolves).
    save_yaml(paths.drift_notification_state_file, {
        "codes": current_codes,
        "updated_at": now_iso(),
    })

    if not current_codes:
        return

    # Only notify on TRANSITION: new codes that weren't in the previous set.
    new_codes = set(current_codes) - set(prev_codes)
    if not new_codes:
        return

    drift_alerts = [a for a in alerts if a.get("source") == "drift"]
    if not drift_alerts:
        return

    # Pending notification already queued for the hook — don't double-write.
    if paths.pending_notification_file.exists():
        return

    from keel.session.ui import _vibe
    top = drift_alerts[0]
    message = _vibe(top.get("summary", "drifting"))
    if replan_suggested:
        message = f"{message}\n\u26a0\ufe0f {replan_reason}"
    save_yaml(paths.pending_notification_file, {
        "type": "drift",
        "message": message,
        "created_at": now_iso(),
        "alert_count": len(drift_alerts),
        "replan_suggested": replan_suggested,
        "new_codes": sorted(new_codes),
    })


def write_companion_heartbeat(
    paths: KeelPaths,
    *,
    token: Optional[str],
    result: dict[str, object],
    fingerprint: Optional[str],
    latest_change_at: Optional[str],
) -> None:
    payload = {
        "token": token,
        "updated_at": now_iso(),
        "status": result.get("status"),
        "validation_status": result.get("validation_status"),
        "drift_status": result.get("drift_status"),
        "current_next_step": result.get("current_next_step"),
        "active_goal_id": result.get("active_goal_id"),
        "repo_fingerprint": fingerprint,
        "latest_repo_change_at": latest_change_at,
    }
    save_yaml(paths.companion_heartbeat_file, payload)


def run_awareness_pass(
    *,
    paths: KeelPaths,
    config: KeelConfig,
    session: SessionState,
    drift_mode: str = "auto",
) -> dict[str, object]:
    bundle = load_active_bundle(paths, session)
    goal = bundle["goal"]
    plan = bundle["plan"]
    questions = bundle["questions"]
    deltas = [
        _preferred_model(paths.deltas_dir, artifact.stem, DeltaArtifact)
        for artifact in sorted(paths.deltas_dir.glob("*.yaml"))
    ]
    deltas = [artifact for artifact in deltas if artifact is not None]

    validation = run_validation(
        paths=paths,
        config=config,
        goal=goal,
        plan=plan,
        questions=questions,
        deltas=deltas,
    )
    validation_path = save_artifact(paths, paths.reports_dir / "validation", "validation", validation)

    trace = build_trace(
        repo_root=".",
        goal=goal,
        plan=plan,
        validation=validation,
    )
    trace_path = save_artifact(paths, paths.reports_dir / "trace", "trace", trace)

    drift = detect_drift(
        paths=paths,
        session=session,
        scan=bundle["scan"],
        goal=goal,
        plan=plan,
        questions=questions,
        deltas=deltas,
        mode=drift_mode,
    )
    drift_path = save_artifact(paths, paths.reports_dir / "drift", "drift", drift)

    if plan:
        session.current_next_step = plan.current_next_step
    session.latest_decisions = SessionService(paths).load_decisions()
    session = SessionService(paths).sync_report_state(
        session,
        validation_id=validation.artifact_id,
        drift_id=drift.artifact_id,
        trace_id=trace.artifact_id,
        drift_warnings=[finding.code for finding in drift.findings],
    )
    alerts = update_alert_feed(paths=paths, drift=drift, validation=validation)

    # Auto-replan detection: count warning-or-higher drift findings
    warning_or_higher = {"warning", "error", "blocker"}
    high_severity_count = sum(
        1 for finding in drift.findings if finding.severity.value in warning_or_higher
    )
    replan_suggested = False
    replan_reason = ""
    if high_severity_count >= 5:
        # Check if a replan has happened in the last 10 minutes
        session_service = SessionService(paths)
        recent_decisions = session_service.load_decisions(limit=50)
        now = datetime.now().astimezone()
        replan_recent = False
        for line in recent_decisions:
            if "replan" in line.lower():
                replan_recent = True
                break
        # Also check raw decisions log for timestamps within 10 minutes
        if replan_recent:
            raw_lines = []
            if paths.decisions_log_file.exists():
                raw_lines = [
                    line.strip()
                    for line in paths.decisions_log_file.read_text(encoding="utf-8").splitlines()
                    if line.strip() and "replan" in line.lower()
                ]
            replan_recent = False
            for raw_line in raw_lines:
                parts = raw_line.split(" ", 1)
                if len(parts) == 2:
                    try:
                        decision_time = datetime.fromisoformat(parts[0])
                        if (now - decision_time).total_seconds() < 600:
                            replan_recent = True
                            break
                    except (ValueError, TypeError):
                        continue
        if not replan_recent:
            replan_suggested = True
            replan_reason = "5+ drift warnings without replan \u2014 consider running keel replan"

    _write_drift_notification(paths, drift, alerts, replan_suggested=replan_suggested, replan_reason=replan_reason)
    brief_path = refresh_current_brief(paths, session, validation=validation, drift=drift)

    overall_status = "clear"
    if validation.status == "error" or drift.status == "blocked":
        overall_status = "blocked"
    elif validation.status == "warning" or drift.status == "warning":
        overall_status = "warning"

    return {
        "status": overall_status,
        "validation_status": validation.status,
        "validation_id": validation.artifact_id,
        "validation_path": str(validation_path),
        "validation_findings": [finding.code for finding in validation.findings],
        "drift_status": drift.status,
        "drift_id": drift.artifact_id,
        "drift_path": str(drift_path),
        "drift_findings": [finding.code for finding in drift.findings],
        "trace_id": trace.artifact_id,
        "trace_path": str(trace_path),
        "trace_rows": len(trace.rows),
        "brief": str(brief_path),
        "active_goal_id": session.active_goal_id,
        "current_next_step": session.current_next_step,
        "alerts_count": len(alerts),
        "recent_alerts": alerts,
        "replan_suggested": replan_suggested,
        "replan_reason": replan_reason,
    }
