from __future__ import annotations

import os
import site
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from keel.baseline import build_baseline
from keel.config import load_config
from keel.core.artifacts import (
    load_latest_model,
    load_model_by_artifact_id,
    load_model,
    save_artifact,
)
from keel.core.bootstrap import ensure_project
from keel.core.paths import resolve_paths
from keel.discovery import scan_repository
from keel.drift import clear_managed_install_drift, detect_drift, dismiss_drift_codes
from keel.goal import build_goal
from keel.models import (
    AlignmentArtifact,
    BaselineArtifact,
    DeltaArtifact,
    DriftArtifact,
    GoalArtifact,
    GoalMode,
    PlanArtifact,
    QuestionArtifact,
    RecoveryArtifact,
    ResearchArtifact,
    ScanArtifact,
    SessionState,
    TraceArtifact,
    ValidationArtifact,
)
from keel.planner import build_plan
from keel.recover import build_recovery
from keel.reporters import render_artifact, render_result
from keel.rules import CONFIDENCE_EXPLANATIONS, ERROR_CODES
from keel.session import (
    SessionService,
    companion_status,
    install_git_hooks,
    latest_repo_change_at,
    load_active_alerts,
    load_active_bundle,
    refresh_current_brief,
    repo_watch_fingerprint,
    run_awareness_pass,
    start_companion,
    stop_companion,
    write_companion_heartbeat,
)
from keel.trace import build_trace
from keel.utils import install_agent_assets
from keel.validators import run_validation

app = typer.Typer(add_completion=False, help="KEEL: a local-first discovery and anti-drift CLI.")
companion_app = typer.Typer(help="Manage the local KEEL companion process.")
app.add_typer(companion_app, name="companion")
console = Console()


class AppState:
    def __init__(self, repo: Path, json_output: bool):
        self.repo = repo
        self.json_output = json_output


def _ctx(ctx: typer.Context) -> AppState:
    return ctx.obj


def _split(values: Optional[List[str]]) -> list[str]:
    return list(values or [])


def _paths(state: AppState):
    return resolve_paths(state.repo)


def _load_latest(paths, model_type, directory):
    return load_latest_model(directory, model_type)


def _load_all_deltas(paths) -> list[DeltaArtifact]:
    items = []
    for path in sorted(paths.deltas_dir.glob("*.yaml")):
        items.append(load_model(path, DeltaArtifact))
    return items


def _save_and_render(paths, artifact, directory, prefix, state: AppState, lines: list[str]):
    artifact_path = save_artifact(paths, directory, prefix, artifact)
    render_artifact(
        console,
        artifact,
        state.json_output,
        [*lines, f"artifact: {artifact_path.relative_to(paths.root)}"],
    )
    return artifact


def _current_session(paths) -> SessionState:
    return SessionService(paths).load()


def _load_preferred_report(paths, session: SessionState, model_type, directory, session_attr: str):
    artifact_id = getattr(session, session_attr, None)
    if artifact_id:
        model = load_model_by_artifact_id(directory, artifact_id, model_type)
        if model is not None:
            return model
    return _load_latest(paths, model_type, directory)


def _refresh_brief(paths) -> None:
    session = SessionService(paths).load()
    refresh_current_brief(paths, session)
    # Mirror the brief into .planning/KEEL-STATUS.md for GSD agents
    brief_file = paths.current_brief_file
    if brief_file.exists():
        from keel.bridge.gsd import write_keel_brief_to_planning
        write_keel_brief_to_planning(paths.root, brief_file.read_text(encoding="utf-8"))


def _install_session_handoff(paths, config, session: SessionState) -> dict[str, object] | None:
    if not session.active_goal_id:
        return None

    result = run_awareness_pass(paths=paths, config=config, session=session, drift_mode="auto")
    stale = result["drift_status"] != "clear"
    recommended = "keel recover" if stale else "none"
    alternate = "keel replan" if stale else "none"
    reason = (
        "The saved KEEL goal and plan no longer cleanly match the current repo state."
        if stale
        else "The saved KEEL goal and plan still look aligned with the current repo state."
    )
    return {
        "active_goal_id": session.active_goal_id,
        "current_next_step": result.get("current_next_step") or session.current_next_step,
        "status": result["status"],
        "drift_status": result["drift_status"],
        "validation_status": result["validation_status"],
        "stale_session_detected": stale,
        "reason": reason,
        "recommended_command": recommended,
        "alternate_command": alternate,
        "alerts_count": result.get("alerts_count", 0),
        "drift_findings": result.get("drift_findings", []),
    }


def _preinstall_checkpoint(paths, session: SessionState) -> str | None:
    if not (session.active_goal_id or session.active_plan_id or session.latest_scan_id):
        return None
    service = SessionService(paths)
    note = "KEEL install auto-checkpoint before companion bootstrap"
    service.add_checkpoint(note, session)
    service.record_decision(session, note)
    return note


def _install_bootstrap_paths(repo_root: Path, messages: list[str]) -> list[str]:
    prefixes = ("Bootstrapped repo-local agent file ", "Updated repo-local agent file ")
    rows = []
    for message in messages:
        prefix = None
        for value in prefixes:
            if message.startswith(value):
                prefix = value
                break
        if prefix is None:
            continue
        target = Path(message[len(prefix) :].strip())
        try:
            rows.append(str(target.relative_to(repo_root)))
        except ValueError:
            continue
    return rows


def _record_install_bootstrap(paths, session: SessionState, changed_paths: list[str]) -> None:
    if not changed_paths:
        return
    artifact = DeltaArtifact(
        artifact_id=f"delta-install-bootstrap-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=".",
        summary="Bootstrap KEEL companion assets for this repo",
        impacted_paths=changed_paths,
        acceptance_criteria=[
            "Repo-local Claude and Codex companion files are installed and intentionally tracked.",
            "The first KEEL awareness pass after install starts from a clean post-bootstrap checkpoint.",
        ],
        validation_mapping=[
            "Install-time checkpoint records KEEL-managed bootstrap changes before drift detection resumes.",
        ],
    )
    save_artifact(paths, paths.deltas_dir, "delta", artifact)
    service = SessionService(paths)
    service.add_checkpoint("KEEL install bootstrap", session, kind="install-bootstrap")
    service.record_decision(session, "Recorded KEEL-managed install bootstrap delta and checkpoint.")


def _install_path_guidance() -> list[str]:
    user_bin = Path(site.getuserbase()) / "bin"
    path_dirs = [Path(entry).expanduser() for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    if any(path_dir == user_bin for path_dir in path_dirs):
        return []
    return [
        f"`keel` may not be on PATH yet. Add this to your shell: export PATH=\"{user_bin}:$PATH\"",
        "Fallback: run KEEL with `python3 -m keel` if the binary is not available yet.",
    ]


def _latest_bundle(paths):
    return {
        "scan": _load_latest(paths, ScanArtifact, paths.scans_dir),
        "baseline": _load_latest(paths, BaselineArtifact, paths.baselines_dir),
        "goal": _load_latest(paths, GoalArtifact, paths.goals_dir),
        "research": _load_latest(paths, ResearchArtifact, paths.research_artifacts_dir),
        "questions": _load_latest(paths, QuestionArtifact, paths.questions_dir),
        "alignment": _load_latest(paths, AlignmentArtifact, paths.alignments_dir),
        "plan": _load_latest(paths, PlanArtifact, paths.plans_dir),
        "trace": _load_latest(paths, TraceArtifact, paths.reports_dir / "trace"),
        "validation": _load_latest(paths, ValidationArtifact, paths.reports_dir / "validation"),
        "drift": _load_latest(paths, DriftArtifact, paths.reports_dir / "drift"),
    }


def _collect_list(prompt_text: str) -> list[str]:
    items = []
    while True:
        value = typer.prompt(prompt_text, default="", show_default=False).strip()
        if not value:
            break
        items.append(value)
    return items





@app.callback()
def main_callback(
    ctx: typer.Context,
    repo: Annotated[Path, typer.Option("--repo", help="Repository root to inspect.")] = Path("."),
    json: Annotated[bool, typer.Option("--json", help="Emit stable JSON output.")] = False,
) -> None:
    ctx.obj = AppState(repo.resolve(), json)


@app.command()
def init(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, config, session = ensure_project(state.repo)
    from keel.bridge.gsd import gsd_present
    gsd_notice = "GSD detected — KEEL will read .planning/ for phase context" if gsd_present(state.repo) else None
    if not config.research_enabled:
        console.print("[dim]research: disabled (set research_enabled: true in .keel/config.yaml to enable)[/dim]")
    if gsd_notice:
        console.print(f"[dim]{gsd_notice}[/dim]")
    render_result(
        console,
        "Init",
        [
            f"repo: {paths.root}",
            f"strictness: {config.strictness.value}",
            f"session file: {paths.current_file.relative_to(paths.root)}",
            f"active goal: {session.active_goal_id or 'none'}",
        ],
        state.json_output,
        {
            "status": "initialized",
            "repo_root": str(paths.root),
            "strictness": config.strictness.value,
            "session_file": str(paths.current_file),
        },
    )


@app.command()
def scan(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, config, _ = ensure_project(state.repo)
    artifact = scan_repository(paths.root, config)
    _save_and_render(
        paths,
        artifact,
        paths.scans_dir,
        "scan",
        state,
        [
            f"files: {artifact.stats.file_count}",
            f"languages: {', '.join(item.name for item in artifact.languages) or 'none'}",
            f"entrypoints: {', '.join(item.name for item in artifact.entrypoints[:4]) or 'none'}",
            f"findings: {len(artifact.findings)}",
        ],
    )


@app.command()
def baseline(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, _, _ = ensure_project(state.repo)
    scan_artifact = _load_latest(paths, ScanArtifact, paths.scans_dir)
    if not scan_artifact:
        raise typer.Exit(code=1)
    artifact = build_baseline(scan_artifact)
    _save_and_render(
        paths,
        artifact,
        paths.baselines_dir,
        "baseline",
        state,
        [
            f"exists today: {len(artifact.exists_today)}",
            f"authoritative signals: {len(artifact.authoritative)}",
            f"unknowns: {len(artifact.unknowns)}",
        ],
    )


@app.command()
def goal(
    ctx: typer.Context,
    goal_mode: Annotated[GoalMode, typer.Option("--goal-mode")] = GoalMode.UNDERSTAND,
    goal_statement: Annotated[Optional[str], typer.Option("--goal-statement")] = None,
    scope: Annotated[Optional[List[str]], typer.Option("--scope")] = None,
    out_of_scope: Annotated[Optional[List[str]], typer.Option("--out-of-scope")] = None,
    constraint: Annotated[Optional[List[str]], typer.Option("--constraint")] = None,
    success_criterion: Annotated[Optional[List[str]], typer.Option("--success-criterion")] = None,
    risk: Annotated[Optional[List[str]], typer.Option("--risk")] = None,
    assumption: Annotated[Optional[List[str]], typer.Option("--assumption")] = None,
    unresolved_question: Annotated[Optional[List[str]], typer.Option("--unresolved-question")] = None,
) -> None:
    state = _ctx(ctx)
    paths, _, session = ensure_project(state.repo)

    # Guard: if only question flags were passed (no --goal-statement) and a goal
    # already exists, do NOT silently overwrite it with a generic default.
    only_questions = (
        goal_statement is None
        and not scope and not out_of_scope and not constraint
        and not success_criterion and not risk and not assumption
        and unresolved_question
        and session.active_goal_id
    )
    if only_questions:
        existing = load_model_by_artifact_id(paths.goals_dir, session.active_goal_id, GoalArtifact)
        if existing:
            # Append questions to the existing goal instead of replacing it
            updated_questions = list(existing.unresolved_questions or []) + list(_split(unresolved_question) or [])
            artifact = build_goal(
                repo_root=".",
                mode=existing.mode,
                goal_statement=existing.goal_statement,
                scope=existing.scope or [],
                out_of_scope=existing.out_of_scope or [],
                constraints=existing.constraints or [],
                success_criteria=existing.success_criteria or [],
                risks=existing.risks or [],
                assumptions=existing.assumptions or [],
                unresolved_questions=updated_questions,
            )
            _save_and_render(paths, artifact, paths.goals_dir, "goal", state,
                             [f"mode: {artifact.mode.value}", f"goal: {artifact.goal_statement}",
                              f"added questions: {len(_split(unresolved_question) or [])}"])
            from keel.session.service import SessionService
            svc = SessionService(paths)
            s = svc.load()
            s.active_goal_id = artifact.artifact_id
            svc.save(s)
            _refresh_brief(paths)
            return

    # REQ-101: If an active goal exists and no --goal-statement was given,
    # inherit the existing goal_statement rather than silently applying a default.
    if goal_statement is None and session.active_goal_id:
        _existing_for_stmt = load_model_by_artifact_id(
            paths.goals_dir, session.active_goal_id, GoalArtifact
        )
        if _existing_for_stmt:
            goal_statement = _existing_for_stmt.goal_statement

    # If no goal statement given, try to pull from the active GSD phase
    if goal_statement is None:
        from keel.bridge.gsd import sync_goal_from_gsd
        gsd_goal = sync_goal_from_gsd(state.repo)
        if gsd_goal:
            goal_statement = gsd_goal
            console.print(f"[dim]Using GSD phase goal: {gsd_goal}[/dim]")

    artifact = build_goal(
        repo_root=".",
        mode=goal_mode,
        goal_statement=goal_statement,
        scope=_split(scope),
        out_of_scope=_split(out_of_scope),
        constraints=_split(constraint),
        success_criteria=_split(success_criterion),
        risks=_split(risk),
        assumptions=_split(assumption),
        unresolved_questions=_split(unresolved_question),
    )
    _save_and_render(
        paths,
        artifact,
        paths.goals_dir,
        "goal",
        state,
        [
            f"mode: {artifact.mode.value}",
            f"goal: {artifact.goal_statement}",
            f"success criteria: {len(artifact.success_criteria)}",
        ],
    )
    # Auto-activate the new goal
    from keel.session.service import SessionService
    svc = SessionService(paths)
    session = svc.load()
    session.active_goal_id = artifact.artifact_id
    svc.save(session)
    _refresh_brief(paths)








@app.command()
def plan(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, _, _ = ensure_project(state.repo)
    bundle = _latest_bundle(paths)
    artifact = build_plan(
        repo_root=".",
        scan=bundle["scan"],
        baseline=bundle["baseline"],
        goal=bundle["goal"],
        alignment=bundle["alignment"],
        questions=bundle["questions"],
    )
    _save_and_render(
        paths,
        artifact,
        paths.plans_dir,
        "plan",
        state,
        [
            f"phases: {len(artifact.phases)}",
            f"next: {artifact.current_next_step}",
        ],
    )
    # Auto-activate the new plan
    from keel.session.service import SessionService
    svc = SessionService(paths)
    session = svc.load()
    session.active_plan_id = artifact.artifact_id
    session.current_next_step = artifact.current_next_step
    if artifact.phases:
        session.active_phase_id = artifact.phases[0].phase_id
        if artifact.phases[0].steps:
            session.active_step_id = artifact.phases[0].steps[0].step_id
    svc.save(session)
    _refresh_brief(paths)




@app.command()
def checkpoint(
    ctx: typer.Context,
    note: Annotated[str, typer.Option("--note", help="Short note for the checkpoint.")] = "manual checkpoint",
) -> None:
    state = _ctx(ctx)
    paths, _, session = ensure_project(state.repo)
    SessionService(paths).add_checkpoint(note, session)
    session = SessionService(paths).record_decision(session, f"Checkpoint: {note}")
    _refresh_brief(paths)
    render_result(
        console,
        "Checkpoint",
        [f"saved: {note}"],
        state.json_output,
        {"status": "saved", "note": note, "checkpoint_file": str(paths.checkpoints_file)},
    )


@app.command()
def replan(ctx: typer.Context) -> None:
    plan(ctx)


@app.command()
def advance(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, _, session = ensure_project(state.repo)
    plan_artifact = _load_latest(paths, PlanArtifact, paths.plans_dir)
    if not plan_artifact:
        render_result(
            console,
            "Advance",
            ["No active plan found. Run keel start or keel plan first."],
            state.json_output,
            {"status": "error", "message": "No active plan found."},
        )
        raise typer.Exit(code=1)

    old_step_id = session.active_step_id
    old_phase_id = session.active_phase_id
    service = SessionService(paths)
    session, message = service.advance_step(session, plan_artifact)

    service.add_checkpoint(f"Completed step: {old_step_id}", session, kind="advance")
    service.record_decision(session, f"Advanced plan: completed {old_step_id}, now at {session.active_step_id or 'done'}")
    refresh_current_brief(paths, session)

    # Determine new phase title for display
    new_phase_title = None
    if session.active_phase_id:
        for phase in plan_artifact.phases:
            if phase.phase_id == session.active_phase_id:
                new_phase_title = phase.title
                break

    render_result(
        console,
        "Advance",
        [
            f"completed: {old_step_id}",
            f"phase: {new_phase_title or 'complete'}",
            f"next: {session.current_next_step or message}",
        ],
        state.json_output,
        {
            "status": "advanced",
            "completed_step_id": old_step_id,
            "completed_phase_id": old_phase_id,
            "active_step_id": session.active_step_id,
            "active_phase_id": session.active_phase_id,
            "current_next_step": session.current_next_step,
            "message": message,
        },
    )


@app.command()
def validate(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON output for this command.")] = False,
) -> None:
    state = _ctx(ctx)
    state.json_output = state.json_output or json_output
    paths, config, session = ensure_project(state.repo)
    bundle = _latest_bundle(paths)
    artifact = run_validation(
        paths=paths,
        config=config,
        goal=bundle["goal"],
        plan=bundle["plan"],
        questions=bundle["questions"],
        deltas=_load_all_deltas(paths),
    )
    report_dir = paths.reports_dir / "validation"
    report_dir.mkdir(parents=True, exist_ok=True)
    _save_and_render(
        paths,
        artifact,
        report_dir,
        "validation",
        state,
        [
            f"status: {artifact.status}",
            f"findings: {len(artifact.findings)}",
        ],
    )
    SessionService(paths).sync_report_state(session, validation_id=artifact.artifact_id)
    _refresh_brief(paths)




@app.command()
def trace(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON output for this command.")] = False,
) -> None:
    state = _ctx(ctx)
    state.json_output = state.json_output or json_output
    paths, _, session = ensure_project(state.repo)
    bundle = _latest_bundle(paths)
    artifact = build_trace(
        repo_root=".",
        goal=bundle["goal"],
        plan=bundle["plan"],
        validation=bundle["validation"],
    )
    report_dir = paths.reports_dir / "trace"
    report_dir.mkdir(parents=True, exist_ok=True)
    _save_and_render(
        paths,
        artifact,
        report_dir,
        "trace",
        state,
        [
            f"rows: {len(artifact.rows)}",
            f"status: {'linked' if artifact.rows else 'empty'}",
        ],
    )
    SessionService(paths).sync_report_state(session, trace_id=artifact.artifact_id)


@app.command()
def drift(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON output for this command.")] = False,
    mode: Annotated[str, typer.Option("--mode", help="soft, hard, or auto")] = "auto",
    dismiss: Annotated[Optional[List[str]], typer.Option("--dismiss", help="Temporarily dismiss one or more drift codes.")] = None,
    dismiss_for_minutes: Annotated[int, typer.Option("--dismiss-for-minutes", min=1, help="How long a dismissal should stay active.")] = 30,
) -> None:
    state = _ctx(ctx)
    state.json_output = state.json_output or json_output
    paths, _, session = ensure_project(state.repo)
    if dismiss:
        rows = dismiss_drift_codes(paths, codes=_split(dismiss), minutes=dismiss_for_minutes)
        render_result(
            console,
            "Drift Dismiss",
            [f"dismissed: {', '.join(row['code'] for row in rows)}", f"for: {dismiss_for_minutes} minutes"],
            state.json_output,
            {"status": "dismissed", "dismissals": rows},
        )
        return
    bundle = _latest_bundle(paths)
    artifact = detect_drift(
        paths=paths,
        session=session,
        scan=bundle["scan"],
        goal=bundle["goal"],
        plan=bundle["plan"],
        questions=bundle["questions"],
        deltas=_load_all_deltas(paths),
        mode=mode,
    )
    report_dir = paths.reports_dir / "drift"
    report_dir.mkdir(parents=True, exist_ok=True)
    _save_and_render(
        paths,
        artifact,
        report_dir,
        "drift",
        state,
        [
            f"status: {artifact.status}",
            f"mode: {artifact.mode}",
            f"findings: {len(artifact.findings)}",
            f"clusters: {len(artifact.clusters)}",
        ],
    )
    SessionService(paths).sync_report_state(
        session,
        drift_id=artifact.artifact_id,
        drift_warnings=[finding.code for finding in artifact.findings],
    )
    _refresh_brief(paths)


@app.command()
def delta(
    ctx: typer.Context,
    summary_text: Optional[str] = typer.Argument(None, help="Delta summary."),
    summary: Optional[str] = typer.Option(None, "--summary", help="Delta summary."),
    impacted_path: Annotated[Optional[List[str]], typer.Option("--impacted-path")] = None,
    acceptance_criterion: Annotated[Optional[List[str]], typer.Option("--acceptance-criterion")] = None,
    validation_mapping: Annotated[Optional[List[str]], typer.Option("--validation-mapping")] = None,
) -> None:
    state = _ctx(ctx)
    paths, _, _ = ensure_project(state.repo)
    resolved_summary = summary or summary_text
    if not resolved_summary:
        raise typer.BadParameter("Provide a delta summary either positionally or with --summary.")
    artifact = DeltaArtifact(
        artifact_id=f"delta-{Path(paths.root).name}-{resolved_summary.lower().replace(' ', '-')[:24]}",
        created_at=__import__("datetime").datetime.now().astimezone(),
        repo_root=".",
        summary=resolved_summary,
        impacted_paths=_split(impacted_path),
        acceptance_criteria=_split(acceptance_criterion),
        validation_mapping=_split(validation_mapping),
    )
    _save_and_render(
        paths,
        artifact,
        paths.deltas_dir,
        "delta",
        state,
        [
            f"summary: {artifact.summary}",
            f"acceptance criteria: {len(artifact.acceptance_criteria)}",
        ],
    )


@app.command()
def done(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, config, session = ensure_project(state.repo)
    validation_artifact = _load_preferred_report(
        paths,
        session,
        ValidationArtifact,
        paths.reports_dir / "validation",
        "latest_validation_id",
    )
    drift_artifact = _load_preferred_report(
        paths,
        session,
        DriftArtifact,
        paths.reports_dir / "drift",
        "latest_drift_id",
    )
    blockers = []
    if validation_artifact and validation_artifact.status == "error":
        blockers.append("validation")
    if validation_artifact and config.strictness.value in {"strict", "paranoid"} and validation_artifact.status == "warning":
        blockers.append("validation")
    if drift_artifact and (
        drift_artifact.status == "blocked"
        or any(
            finding.code in {"KEE-DRF-003", "KEE-DRF-009", "KEE-DRF-014"}
            for finding in drift_artifact.findings
        )
    ):
        blockers.append("drift")
    if drift_artifact and config.strictness.value in {"strict", "paranoid"} and drift_artifact.status == "warning":
        blockers.append("drift")
    status = "blocked" if blockers else "clear"
    render_result(
        console,
        "Done",
        [
            f"status: {status}",
            f"blockers: {', '.join(blockers) if blockers else 'none'}",
        ],
        state.json_output,
        {
            "status": status,
            "blockers": blockers,
            "error_code": None if not blockers else "KEE-DNE-001",
        },
    )


@app.command()
def doctor(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, config, _ = ensure_project(state.repo)
    render_result(
        console,
        "Doctor",
        [
            f"repo: {paths.root}",
            f"config: {paths.config_file.relative_to(paths.root)}",
            f"strictness: {config.strictness.value}",
            f"research enabled: {config.research_enabled}",
        ],
        state.json_output,
        {
            "repo_root": str(paths.root),
            "config_file": str(paths.config_file),
            "strictness": config.strictness.value,
            "research_enabled": config.research_enabled,
        },
    )




@app.command()
def status(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, _, session = ensure_project(state.repo)
    companion = companion_status(paths)
    alerts = load_active_alerts(paths)
    render_result(
        console,
        "Status",
        [
            f"goal: {session.active_goal_id or 'none'}",
            f"plan: {session.active_plan_id or 'none'}",
            f"next: {session.current_next_step or 'none'}",
            f"companion: {'running' if companion.get('running') else 'stopped'}",
            f"alerts: {len(alerts)} active",
            f"brief: {paths.current_brief_file.relative_to(paths.root)}",
        ],
        state.json_output,
        {
            **session.model_dump(mode="json", exclude_none=True),
            "companion": companion,
            "alerts_count": len(alerts),
            "recent_alerts": alerts,
        },
    )


@app.command()
def watch(
    ctx: typer.Context,
    mode: Annotated[str, typer.Option("--mode", help="soft, hard, or auto")] = "auto",
    interval: Annotated[float, typer.Option("--interval", min=0.2, help="Polling interval in seconds.")] = 2.0,
    once: Annotated[bool, typer.Option("--once", help="Run one awareness pass and exit.")] = False,
    max_cycles: Annotated[Optional[int], typer.Option("--max-cycles", min=1, help="Stop after this many polling cycles.")] = None,
    heartbeat_file: Annotated[Optional[Path], typer.Option("--heartbeat-file", hidden=True)] = None,
    companion_token: Annotated[Optional[str], typer.Option("--companion-token", hidden=True)] = None,
) -> None:
    state = _ctx(ctx)
    if state.json_output and not once:
        raise typer.BadParameter("`keel watch --json` requires `--once` for stable output.")

    paths, config, session = ensure_project(state.repo)
    events_observed = 0
    last_fingerprint = repo_watch_fingerprint(paths, config)
    result = run_awareness_pass(paths=paths, config=config, session=session, drift_mode=mode)
    latest_change_at = latest_repo_change_at(paths, config)
    if heartbeat_file:
        write_companion_heartbeat(
            paths,
            token=companion_token,
            result=result,
            fingerprint=last_fingerprint,
            latest_change_at=latest_change_at,
        )
    events_observed += 1

    if once:
        render_result(
            console,
            "Watch",
            [
                f"status: {result['status']}",
                f"validation: {result['validation_status']}",
                f"drift: {result['drift_status']}",
                f"brief: {Path(str(result['brief'])).relative_to(paths.root)}",
            ],
            state.json_output,
            {**result, "events_observed": events_observed, "mode": "once"},
        )
        return

    render_result(
        console,
        "Watch",
        [
            f"watching: {paths.root}",
            f"validation: {result['validation_status']}",
            f"drift: {result['drift_status']}",
            f"next: {result['current_next_step'] or 'none'}",
        ],
        False,
        {},
    )
    console.print(f"Polling every {interval:.1f}s. Press Ctrl+C to stop.")

    cycles = 0
    consecutive_errors = 0
    max_consecutive_errors = 10
    exit_reason = "unknown"
    try:
        while max_cycles is None or cycles < max_cycles:
            sleep_time = interval * min(2 ** consecutive_errors, 30) if consecutive_errors > 0 else interval
            time.sleep(sleep_time)
            cycles += 1
            try:
                fingerprint = repo_watch_fingerprint(paths, config)
                if fingerprint == last_fingerprint:
                    if heartbeat_file:
                        write_companion_heartbeat(
                            paths,
                            token=companion_token,
                            result=result,
                            fingerprint=fingerprint,
                            latest_change_at=latest_repo_change_at(paths, config),
                        )
                    consecutive_errors = 0
                    continue
                last_fingerprint = fingerprint
                session = SessionService(paths).load()
                result = run_awareness_pass(paths=paths, config=config, session=session, drift_mode=mode)
                if heartbeat_file:
                    write_companion_heartbeat(
                        paths,
                        token=companion_token,
                        result=result,
                        fingerprint=fingerprint,
                        latest_change_at=latest_repo_change_at(paths, config),
                    )
                events_observed += 1
                consecutive_errors = 0
                render_result(
                    console,
                    "Watch Update",
                    [
                        f"status: {result['status']}",
                        f"validation: {result['validation_status']}",
                        f"drift: {result['drift_status']}",
                        f"brief: {Path(str(result['brief'])).relative_to(paths.root)}",
                    ],
                    False,
                    {},
                )
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                consecutive_errors += 1
                console.print(f"[dim]watch: error on cycle {cycles}: {exc}[/dim]")
                if consecutive_errors >= max_consecutive_errors:
                    exit_reason = f"too many consecutive errors ({consecutive_errors}): {exc}"
                    break
        else:
            exit_reason = "max_cycles reached" if max_cycles else "loop ended"
        if exit_reason == "unknown":
            exit_reason = "loop exited normally"
    except KeyboardInterrupt:
        exit_reason = "user interrupt"
        console.print("Stopped KEEL watch.")
    except Exception as exc:
        exit_reason = f"fatal: {exc}"
    finally:
        # Always log the exit reason so silent deaths are diagnosable
        try:
            with paths.companion_log_file.open("a", encoding="utf-8") as log:
                from keel.core.paths import now_iso
                log.write(f"[{now_iso()}] companion exited: {exit_reason} (cycles={cycles}, events={events_observed})\n")
        except Exception:
            pass


@companion_app.command("start")
def companion_start(
    ctx: typer.Context,
    interval: Annotated[float, typer.Option("--interval", min=0.2, help="Polling interval in seconds.")] = 2.0,
    mode: Annotated[str, typer.Option("--mode", help="soft, hard, or auto")] = "auto",
    install_repo_hooks_flag: Annotated[bool, typer.Option("--install-repo-hooks/--skip-repo-hooks", help="Install repo git hooks before starting the companion.")] = True,
) -> None:
    state = _ctx(ctx)
    paths, _, _ = ensure_project(state.repo)
    lines = []
    if install_repo_hooks_flag:
        lines.extend(install_git_hooks(paths))
    status = start_companion(paths, interval=interval, mode=mode)
    lines.append(f"companion: {'running' if status.get('running') else 'failed'}")
    if not status.get("running"):
        lines.append("retry: keel companion start")
    lines.append(f"log: {paths.companion_log_file.relative_to(paths.root)}")
    render_result(console, "Companion Start", lines, state.json_output, status)


@companion_app.command("stop")
def companion_stop(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, _, _ = ensure_project(state.repo)
    status = stop_companion(paths)
    render_result(
        console,
        "Companion Stop",
        [
            "companion: stopped",
            f"log: {paths.companion_log_file.relative_to(paths.root)}",
        ],
        state.json_output,
        status,
    )


@companion_app.command("status")
def companion_status_command(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, _, _ = ensure_project(state.repo)
    status = companion_status(paths)
    render_result(
        console,
        "Companion Status",
        [
            f"companion: {'running' if status.get('running') else 'stopped'}",
            f"fresh: {'yes' if status.get('fresh') else 'no'}",
            f"last awareness: {status.get('last_awareness_at') or 'none'}",
            f"last repo change: {status.get('last_repo_change_at') or 'unknown'}",
            f"log: {paths.companion_log_file.relative_to(paths.root)}",
        ],
        state.json_output,
        status,
    )




@app.command()
def export(
    ctx: typer.Context,
    output: Annotated[Path, typer.Option("--output")] = Path(".keel/reports/export.json"),
) -> None:
    state = _ctx(ctx)
    paths, _, session = ensure_project(state.repo)
    bundle = _latest_bundle(paths)
    payload = {
        "session": session.model_dump(mode="json", exclude_none=True),
        "artifacts": {
            key: value.model_dump(mode="json", exclude_none=True) if value else None
            for key, value in bundle.items()
        },
    }
    target = (paths.root / output).resolve() if not output.is_absolute() else output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(__import__("json").dumps(payload, indent=2), encoding="utf-8")
    render_result(
        console,
        "Export",
        [f"written: {target}"],
        state.json_output,
        {"status": "written", "path": str(target)},
    )


@app.command()
def recover(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON output for this command.")] = False,
) -> None:
    state = _ctx(ctx)
    state.json_output = state.json_output or json_output
    paths, _, session = ensure_project(state.repo)
    drift_artifact = _load_preferred_report(
        paths,
        session,
        DriftArtifact,
        paths.reports_dir / "drift",
        "latest_drift_id",
    )
    if not drift_artifact:
        raise typer.BadParameter("Run `keel drift` before `keel recover` so KEEL has current divergence evidence.")
    validation_artifact = _load_preferred_report(
        paths,
        session,
        ValidationArtifact,
        paths.reports_dir / "validation",
        "latest_validation_id",
    )
    recovery = build_recovery(
        paths=paths,
        session=session,
        goal=_load_latest(paths, GoalArtifact, paths.goals_dir),
        plan=_load_latest(paths, PlanArtifact, paths.plans_dir),
        alignment=_load_latest(paths, AlignmentArtifact, paths.alignments_dir),
        drift=drift_artifact,
        validation=validation_artifact,
    )
    report_dir = paths.reports_dir / "recovery"
    report_dir.mkdir(parents=True, exist_ok=True)
    _save_and_render(
        paths,
        recovery,
        report_dir,
        "recovery",
        state,
        [
            f"recommended mode: {recovery.recommended_mode}",
            f"confidence: {recovery.recovery_confidence.value}",
            f"issues: {len(recovery.issues)}",
            f"steps: {len(recovery.steps)}",
            *[f"step: {step.title}" for step in recovery.steps[:4]],
            f"brief: {Path(recovery.brief_path).relative_to(paths.root)}",
        ],
    )


def _run_install_agents(
    ctx: typer.Context,
    codex_only: Annotated[bool, typer.Option("--codex-only", help="Install only Codex assets.")] = False,
    claude_only: Annotated[bool, typer.Option("--claude-only", help="Install only Claude Code assets.")] = False,
    no_hook: Annotated[bool, typer.Option("--no-hook", help="Skip installing the Claude hook.")] = False,
    no_repo_hooks: Annotated[bool, typer.Option("--no-repo-hooks", help="Skip installing repo git hooks.")] = False,
    with_companion: Annotated[bool, typer.Option("--with-companion/--no-companion", help="Start the local KEEL companion after install.")] = True,
    companion_interval: Annotated[float, typer.Option("--companion-interval", min=0.2, help="Polling interval for the local KEEL companion.")] = 2.0,
    codex_home: Annotated[Optional[Path], typer.Option("--codex-home", help="Override Codex home.")] = None,
    claude_home: Annotated[Optional[Path], typer.Option("--claude-home", help="Override Claude home.")] = None,
) -> None:
    state = _ctx(ctx)
    repo_root = state.repo
    paths, config, session = ensure_project(repo_root)
    preinstall_note = _preinstall_checkpoint(paths, session)
    messages = install_agent_assets(
        repo_root=repo_root,
        install_codex_assets=not claude_only,
        install_claude_assets=not codex_only,
        install_hook=not no_hook,
        install_repo_hooks=not no_repo_hooks,
        start_repo_companion=with_companion,
        companion_interval=companion_interval,
        codex_target=codex_home,
        claude_target=claude_home,
    )
    if preinstall_note:
        messages.insert(0, f"Auto-checkpointed existing KEEL session before install: {preinstall_note}")
    bootstrap_paths = _install_bootstrap_paths(repo_root, messages)
    session = SessionService(paths).load()
    _record_install_bootstrap(paths, session, bootstrap_paths)
    clear_managed_install_drift(paths)
    session = SessionService(paths).load()
    handoff = _install_session_handoff(paths, config, session)
    if bootstrap_paths:
        messages.append(f"KEEL install baseline recorded: {len(bootstrap_paths)} repo-local files acknowledged.")
    if handoff:
        messages.append(f"Active KEEL goal: {handoff['active_goal_id']}")
        messages.append(f"Current next step: {handoff['current_next_step'] or 'none'}")
        if handoff["stale_session_detected"]:
            messages.append("Detected an older active KEEL session that no longer cleanly matches current repo reality.")
            messages.append(f"Recommended now: {handoff['recommended_command']}")
            messages.append(f"If the current repo state is intentional instead, use {handoff['alternate_command']}.")
        else:
            messages.append("Existing KEEL session still looks aligned after install.")
    messages.extend(_install_path_guidance())
    if not messages:
        raise typer.Exit(code=1)
    render_result(
        console,
        "Install Agents",
        messages,
        state.json_output,
        {
            "status": "installed",
            "messages": messages,
            "session_handoff": handoff,
        },
    )


@app.command("install")
def install(
    ctx: typer.Context,
    codex_only: Annotated[bool, typer.Option("--codex-only", help="Install only Codex assets.")] = False,
    claude_only: Annotated[bool, typer.Option("--claude-only", help="Install only Claude Code assets.")] = False,
    no_hook: Annotated[bool, typer.Option("--no-hook", help="Skip installing the Claude hook.")] = False,
    no_repo_hooks: Annotated[bool, typer.Option("--no-repo-hooks", help="Skip installing repo git hooks.")] = False,
    with_companion: Annotated[bool, typer.Option("--with-companion/--no-companion", help="Start the local KEEL companion after install.")] = True,
    companion_interval: Annotated[float, typer.Option("--companion-interval", min=0.2, help="Polling interval for the local KEEL companion.")] = 2.0,
    codex_home: Annotated[Optional[Path], typer.Option("--codex-home", help="Override Codex home.")] = None,
    claude_home: Annotated[Optional[Path], typer.Option("--claude-home", help="Override Claude home.")] = None,
) -> None:
    _run_install_agents(
        ctx=ctx,
        codex_only=codex_only,
        claude_only=claude_only,
        no_hook=no_hook,
        no_repo_hooks=no_repo_hooks,
        with_companion=with_companion,
        companion_interval=companion_interval,
        codex_home=codex_home,
        claude_home=claude_home,
    )


@app.command()
def check(ctx: typer.Context) -> None:
    state = _ctx(ctx)
    paths, config, session = ensure_project(state.repo)
    bundle = load_active_bundle(paths, session)
    validation_artifact = run_validation(
        paths=paths,
        config=config,
        goal=bundle["goal"],
        plan=bundle["plan"],
        questions=bundle["questions"],
        deltas=_load_all_deltas(paths),
    )
    drift_artifact = detect_drift(
        paths=paths,
        session=session,
        scan=bundle["scan"],
        goal=bundle["goal"],
        plan=bundle["plan"],
        questions=bundle["questions"],
        deltas=_load_all_deltas(paths),
    )
    render_result(
        console,
        "Check",
        [
            f"validation: {validation_artifact.status}",
            f"drift: {drift_artifact.status}",
            f"validation findings: {len(validation_artifact.findings)}",
            f"drift findings: {len(drift_artifact.findings)}",
        ],
        state.json_output,
        {
            "validation": validation_artifact.model_dump(mode="json", exclude_none=True),
            "drift": drift_artifact.model_dump(mode="json", exclude_none=True),
        },
    )






