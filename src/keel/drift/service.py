from __future__ import annotations

import hashlib
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Set

from keel.core.artifacts import load_yaml, save_yaml
from keel.core.paths import KeelPaths
from keel.models import (
    ConfidenceLevel,
    DriftCluster,
    DeltaArtifact,
    DriftArtifact,
    DriftFinding,
    GoalArtifact,
    GoalMode,
    PlanArtifact,
    QuestionArtifact,
    ScanArtifact,
    SeverityLevel,
    SessionState,
)


PATTERN_GROUPS = {
    "api-style": {"rest", "graphql", "grpc"},
    "database": {"sqlite", "postgres", "mysql", "mongodb"},
    "runtime": {"sync", "async"},
    "queue": {"celery", "rq", "kafka", "rabbitmq"},
    "deployment": {"docker", "kubernetes", "systemd"},
    "storage": {"local-first", "filesystem", "cloud", "s3"},
}

TERMINOLOGY_GROUPS = {
    "goal": {"goal", "objective", "aim", "target"},
    "plan": {"plan", "roadmap", "phase", "milestone"},
    "requirement": {"requirement", "requirements", "contract", "contracts"},
    "delta": {"delta", "change", "diff"},
    "entrypoint": {"entrypoint", "bootstrap", "startup", "main"},
}


def _severity(level: str) -> SeverityLevel:
    return SeverityLevel.BLOCKER if level == "hard" else SeverityLevel.WARNING


CLUSTER_WINDOW_MINUTES = 10
MAX_MEMORY_EVENTS = 80
DISMISSAL_WINDOW_MINUTES = 30
MANAGED_AGENT_ROOTS = {".claude", ".codex", ".claude-plugin"}
CLUSTER_EMIT_COOLDOWN_MINUTES = 5
IGNORED_BUILD_METADATA_SUFFIXES = {".egg-info"}


def _is_managed_or_ignored_path(path_like: str) -> bool:
    parts = Path(path_like).parts
    if not parts:
        return False
    if parts[0] in MANAGED_AGENT_ROOTS:
        return True
    return any(part.endswith(tuple(IGNORED_BUILD_METADATA_SUFFIXES)) for part in parts)


def _changed_files_since(root: Path, since: datetime) -> list[str]:
    ignored = {".git", ".hg", ".svn", ".keel", "keel", ".pytest_cache"}
    changed = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in ignored]
        for filename in filenames:
            path = Path(current_root) / filename
            try:
                relative = path.relative_to(root)
                if _is_managed_or_ignored_path(str(relative)):
                    continue
                if datetime.fromtimestamp(path.stat().st_mtime, tz=since.tzinfo) > since:
                    changed.append(str(relative))
            except OSError:
                continue
    return sorted(changed)


def _git_has_changes(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return bool(result.stdout.strip())


def _latest_checkpoint_time(paths: KeelPaths) -> Optional[datetime]:
    payload = load_yaml(paths.checkpoints_file)
    checkpoints = payload.get("checkpoints", [])
    if not checkpoints:
        return None
    for checkpoint in reversed(checkpoints):
        if checkpoint.get("kind") == "install-bootstrap":
            continue
        raw = checkpoint.get("created_at")
        return datetime.fromisoformat(raw) if raw else None
    return None


def _active_step(plan: Optional[PlanArtifact], session: SessionState):
    if not plan:
        return None
    for phase in plan.phases:
        for step in phase.steps:
            if step.step_id == session.active_step_id:
                return step
    for phase in plan.phases:
        for step in phase.steps:
            if step.status != "completed":
                return step
    return None


def _path_matches(path: str, candidates: list[str]) -> bool:
    for candidate in candidates:
        normalized = candidate.strip("./")
        if not normalized:
            continue
        if path == normalized or path.startswith(normalized.rstrip("/") + "/"):
            return True
    return False


def _semantic_match(path: str, text: str) -> bool:
    lowered_path = path.lower()
    stem = Path(path).stem.lower()
    top_level = Path(path).parts[0].lower() if Path(path).parts else ""
    tokens = {lowered_path, Path(path).name.lower(), stem, top_level}
    lowered_text = text.lower()
    return any(token and token in lowered_text for token in tokens)


def _artifact_reference_map(paths: KeelPaths, changed_files: list[str]) -> dict[str, list[str]]:
    directories = [
        paths.requirements_dir,
        paths.contracts_dir,
        paths.examples_dir,
        paths.deltas_dir,
        paths.goals_dir,
    ]
    mapping = {path: [] for path in changed_files}
    for directory in directories:
        if not directory.exists():
            continue
        for artifact in directory.glob("*.yaml"):
            try:
                text = artifact.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for changed in changed_files:
                if _semantic_match(changed, text):
                    mapping[changed].append(str(artifact.relative_to(paths.root)))
    return mapping


def _code_like(path: str) -> bool:
    return Path(path).suffix.lower() in {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".swift",
        ".c",
        ".cc",
        ".cpp",
        ".rb",
        ".php",
    }


def _test_like(path: str) -> bool:
    lowered = path.lower()
    return "/tests/" in f"/{lowered}" or lowered.startswith("tests/") or lowered.endswith("_test.py") or lowered.startswith("test_")


def _entrypoint_like(path: str) -> bool:
    lowered = Path(path).name.lower()
    return lowered in {"main.py", "__main__.py", "server.py", "app.py", "cli.py", "manage.py"}


def _entrypoint_family(path: str) -> str:
    lowered = path.lower()
    name = Path(path).name.lower()
    if "/cli/" in f"/{lowered}" or name in {"__main__.py", "main.py", "cli.py"}:
        return "cli"
    if name in {"server.py", "app.py", "asgi.py", "wsgi.py", "manage.py"}:
        return "server"
    return "other"


def _extract_tokens(text: str) -> Set[str]:
    lowered = text.lower()
    hits = set()
    for group_tokens in PATTERN_GROUPS.values():
        for token in group_tokens:
            if token in lowered:
                hits.add(token)
    return hits


def _area_tokens(items: list[str]) -> list[str]:
    areas = []
    for item in items:
        candidate = item.split("=", 1)[0]
        stem = Path(candidate).stem.lower()
        if stem.startswith(("drift", "validation", "trace", "recovery", "export")):
            continue
        if "/" in candidate:
            top_level = Path(candidate).parts[0]
            if top_level == ".keel":
                continue
            areas.append(top_level)
        elif "." in candidate:
            if stem.startswith(("drift", "validation", "trace", "recovery", "export")):
                continue
            areas.append(Path(candidate).stem)
        elif candidate:
            areas.append(candidate[:32])
    ordered = []
    for area in areas:
        if area and area not in ordered:
            ordered.append(area)
    return ordered[:3]


def _cluster_key(layer: str, evidence: list[str]) -> str:
    areas = _area_tokens(evidence) or ["repo"]
    return f"{layer}:{'|'.join(areas)}"


def _managed_only(items: list[str]) -> bool:
    relevant = [item for item in items if item]
    if not relevant:
        return False
    for item in relevant:
        candidate = item.split(":", 1)[0]
        if not _is_managed_or_ignored_path(candidate):
            return False
    return True


def _mentions_managed(items: list[str]) -> bool:
    for item in items:
        if not item:
            continue
        candidate = item.split(":", 1)[0]
        if _is_managed_or_ignored_path(candidate):
            return True
    return False


def _load_recent_events(paths: KeelPaths, now: datetime) -> list[dict]:
    payload = load_yaml(paths.drift_memory_file)
    cutoff = now - timedelta(minutes=CLUSTER_WINDOW_MINUTES)
    recent = []
    for event in payload.get("events", []):
        raw = event.get("seen_at")
        if not raw:
            continue
        try:
            seen_at = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if seen_at >= cutoff:
            recent.append(event)
    return recent


def _load_cluster_emissions(paths: KeelPaths, now: datetime) -> dict[str, dict]:
    payload = load_yaml(paths.drift_memory_file)
    cutoff = now - timedelta(minutes=CLUSTER_WINDOW_MINUTES)
    active: dict[str, dict] = {}
    for key, emission in (payload.get("cluster_emissions", {}) or {}).items():
        raw = emission.get("emitted_at")
        if not raw:
            continue
        try:
            emitted_at = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if emitted_at >= cutoff:
            active[key] = emission
    return active


def _active_dismissals(paths: KeelPaths, now: datetime) -> set[str]:
    payload = load_yaml(paths.drift_dismissals_file)
    active_codes: set[str] = set()
    active_rows: list[dict] = []
    for dismissal in payload.get("dismissals", []):
        code = dismissal.get("code")
        raw_expires_at = dismissal.get("expires_at")
        if not code or not raw_expires_at:
            continue
        try:
            expires_at = datetime.fromisoformat(raw_expires_at)
        except ValueError:
            continue
        if expires_at <= now:
            continue
        active_codes.add(code)
        active_rows.append(dismissal)
    save_yaml(paths.drift_dismissals_file, {"dismissals": active_rows})
    return active_codes


def dismiss_drift_codes(
    paths: KeelPaths,
    *,
    codes: list[str],
    minutes: int = DISMISSAL_WINDOW_MINUTES,
    note: str = "manual dismissal",
) -> list[dict]:
    now = datetime.now().astimezone()
    expires_at = now + timedelta(minutes=max(1, minutes))
    payload = load_yaml(paths.drift_dismissals_file)
    dismissals = payload.get("dismissals", [])
    kept: list[dict] = []
    for dismissal in dismissals:
        raw_expires_at = dismissal.get("expires_at")
        try:
            existing_expires = datetime.fromisoformat(raw_expires_at) if raw_expires_at else None
        except ValueError:
            existing_expires = None
        if existing_expires and existing_expires > now and dismissal.get("code") not in codes:
            kept.append(dismissal)
    new_rows = [
        {
            "code": code,
            "dismissed_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "note": note,
        }
        for code in codes
    ]
    save_yaml(paths.drift_dismissals_file, {"dismissals": kept + new_rows})
    alerts_payload = load_yaml(paths.alerts_file)
    active_alerts = [alert for alert in alerts_payload.get("alerts", []) if alert.get("rule") not in codes]
    save_yaml(paths.alerts_file, {"alerts": active_alerts})
    return new_rows


def clear_managed_install_drift(paths: KeelPaths) -> None:
    payload = load_yaml(paths.drift_memory_file)
    kept_events = []
    for event in payload.get("events", []):
        items = list(event.get("evidence", [])) + list(event.get("changed_files", []))
        if _mentions_managed(items):
            continue
        kept_events.append(event)
    kept_emissions = {}
    for key, emission in (payload.get("cluster_emissions", {}) or {}).items():
        items = list(emission.get("touched_areas", [])) + list(emission.get("related_codes", []))
        if _mentions_managed(items):
            continue
        kept_emissions[key] = emission
    save_yaml(
        paths.drift_memory_file,
        {"events": kept_events[-MAX_MEMORY_EVENTS:], "cluster_emissions": kept_emissions},
    )

    alerts_payload = load_yaml(paths.alerts_file)
    kept_alerts = []
    for alert in alerts_payload.get("alerts", []):
        evidence = list(alert.get("evidence", []))
        if _mentions_managed(evidence):
            continue
        kept_alerts.append(alert)
    save_yaml(paths.alerts_file, {"alerts": kept_alerts[-MAX_MEMORY_EVENTS:]})


def _save_recent_events(paths: KeelPaths, events: list[dict]) -> None:
    payload = load_yaml(paths.drift_memory_file)
    payload["events"] = events[-MAX_MEMORY_EVENTS:]
    save_yaml(paths.drift_memory_file, payload)


def _build_clusters(
    *,
    paths: KeelPaths,
    now: datetime,
    findings: list[DriftFinding],
    changed_files: list[str],
    effective_mode: str,
) -> list[DriftCluster]:
    history = _load_recent_events(paths, now)
    cluster_emissions = _load_cluster_emissions(paths, now)
    current_events = []
    for finding in findings:
        current_events.append(
            {
                "seen_at": now.isoformat(),
                "code": finding.code,
                "layer": finding.layer,
                "severity": finding.severity.value,
                "confidence": finding.confidence.value,
                "summary": finding.summary,
                "evidence": finding.evidence[:8],
                "changed_files": changed_files[:8],
                "cluster_key": _cluster_key(finding.layer, finding.evidence or changed_files),
            }
        )
    all_events = history + current_events
    _save_recent_events(paths, all_events)

    grouped: dict[str, list[dict]] = {}
    for event in all_events:
        grouped.setdefault(event["cluster_key"], []).append(event)

    clusters: list[DriftCluster] = []
    for key, events in grouped.items():
        if len(events) < 3:
            continue
        related_codes = []
        timeline = []
        touched = []
        severities = set()
        confidences = set()
        for event in events:
            code = event["code"]
            if code not in related_codes:
                related_codes.append(code)
            severities.add(event["severity"])
            confidences.add(event["confidence"])
            for area in _area_tokens(event.get("evidence", []) + event.get("changed_files", [])):
                if area not in touched:
                    touched.append(area)
            timeline.append(f"{event['seen_at']}: {event['code']} {event['summary']}")
        if len(related_codes) < 2 and len(events) < 4:
            continue
        first_seen = events[0]["seen_at"]
        last_seen = events[-1]["seen_at"]
        layer = events[-1]["layer"]
        severity = SeverityLevel.WARNING
        if "blocker" in severities or "error" in severities:
            severity = SeverityLevel.BLOCKER
        elif effective_mode == "hard" and len(events) >= 5:
            severity = SeverityLevel.BLOCKER
        confidence = ConfidenceLevel.INFERRED_HIGH if len(events) >= 5 else ConfidenceLevel.INFERRED_MEDIUM
        area_text = ", ".join(touched[:4]) or "repo-wide areas"
        detail = (
            f"Drift signals have been building for about {CLUSTER_WINDOW_MINUTES} minutes. "
            f"First trigger: {first_seen}. Latest related event: {last_seen}. "
            f"Recent signals repeatedly touched {area_text}."
        )
        cluster_id = "cluster-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
        prior = cluster_emissions.get(cluster_id)
        if prior:
            raw_emitted_at = prior.get("emitted_at")
            try:
                emitted_at = datetime.fromisoformat(raw_emitted_at) if raw_emitted_at else None
            except ValueError:
                emitted_at = None
            if emitted_at and emitted_at >= now - timedelta(minutes=CLUSTER_EMIT_COOLDOWN_MINUTES):
                continue
        clusters.append(
            DriftCluster(
                cluster_id=cluster_id,
                layer=layer,
                summary=f"Probable {layer} cluster built from repeated weak signals",
                detail=detail,
                severity=severity,
                confidence=confidence,
                event_count=len(events),
                related_codes=related_codes[:6],
                touched_areas=touched[:6],
                first_seen_at=first_seen,
                last_seen_at=last_seen,
                recommended_action="Checkpoint or replan now before these repeated drift signals turn into a larger alignment break.",
                timeline=timeline[-6:],
            )
        )
        cluster_emissions[cluster_id] = {
            "emitted_at": now.isoformat(),
            "cluster_key": key,
            "related_codes": related_codes[:6],
            "touched_areas": touched[:6],
        }
    payload = load_yaml(paths.drift_memory_file)
    payload["cluster_emissions"] = cluster_emissions
    save_yaml(paths.drift_memory_file, payload)
    return clusters


def _research_drift(
    changed_files: list[str],
    paths: KeelPaths,
    goal: Optional[GoalArtifact],
    findings: list[DriftFinding],
    level: str,
) -> None:
    latest_research_files = sorted(paths.research_artifacts_dir.glob("*.yaml"))
    if not latest_research_files:
        return
    research_payload = latest_research_files[-1].read_text(encoding="utf-8", errors="ignore")
    research_tokens = _extract_tokens(research_payload)
    if not research_tokens:
        return

    changed_text = " ".join(changed_files)
    for path in changed_files[:5]:
        absolute = paths.root / path
        if absolute.exists() and absolute.is_file():
            changed_text += " " + absolute.read_text(encoding="utf-8", errors="ignore")[:400]
    changed_tokens = _extract_tokens(changed_text)
    for group, group_tokens in PATTERN_GROUPS.items():
        research_group = research_tokens & group_tokens
        changed_group = changed_tokens & group_tokens
        if research_group and changed_group and research_group != changed_group:
            findings.append(
                DriftFinding(
                    code="KEE-DRF-006",
                    layer="research drift",
                    summary="Implementation signals moved toward a different design pattern family",
                    detail=(
                        f"Research artifacts lean toward {', '.join(sorted(research_group))}, "
                        f"but recent file changes look closer to {', '.join(sorted(changed_group))}."
                    ),
                    severity=_severity(level),
                    confidence=ConfidenceLevel.HEURISTIC_LOW,
                    suggested_action="Review the active design direction and update the goal, decision record, or research inputs before proceeding.",
                    evidence=changed_files[:5] + [f"goal={goal.mode.value}" if goal else "goal=unknown"],
                )
            )
            return


def _terminology_drift(paths: KeelPaths, changed_files: list[str], findings: list[DriftFinding], level: str) -> None:
    glossary_text = paths.glossary_file.read_text(encoding="utf-8", errors="ignore") if paths.glossary_file.exists() else ""
    canonical_hits = {name: False for name in TERMINOLOGY_GROUPS}
    for canonical, synonyms in TERMINOLOGY_GROUPS.items():
        if any(token in glossary_text.lower() for token in synonyms):
            canonical_hits[canonical] = True

    observed = {name: set() for name in TERMINOLOGY_GROUPS}
    for rel_path in changed_files[:8]:
        path = paths.root / rel_path
        if not path.exists() or not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")[:600].lower()
        for canonical, synonyms in TERMINOLOGY_GROUPS.items():
            for token in synonyms:
                if token in content:
                    observed[canonical].add(token)

    for canonical, tokens in observed.items():
        if len(tokens) > 1 and canonical_hits.get(canonical):
            findings.append(
                DriftFinding(
                    code="KEE-DRF-013",
                    layer="terminology drift",
                    summary="Multiple competing terms appeared for the same concept",
                    detail=f"Changed files are using {', '.join(sorted(tokens))} for the `{canonical}` concept, which can fragment alignment.",
                    severity=SeverityLevel.WARNING if level == "soft" else SeverityLevel.BLOCKER,
                    confidence=ConfidenceLevel.HEURISTIC_LOW,
                    suggested_action="Choose one canonical term in the glossary or artifacts and normalize the active specs and brief.",
                    evidence=changed_files[:5],
                    teaching="Using different words for the same concept fragments understanding. Specs, code, and docs should use the same vocabulary.",
                )
            )
            return


def detect_drift(
    *,
    paths: KeelPaths,
    session: SessionState,
    scan: Optional[ScanArtifact],
    goal: Optional[GoalArtifact],
    plan: Optional[PlanArtifact],
    questions: Optional[QuestionArtifact],
    deltas: Optional[list[DeltaArtifact]] = None,
    mode: str = "soft",
) -> DriftArtifact:
    now = datetime.now().astimezone()
    findings: list[DriftFinding] = []
    deltas = deltas or []

    # No active goal → nothing to drift FROM. Return an empty clean artifact.
    if session.active_goal_id is None:
        return DriftArtifact(
            artifact_id=f"drift-{now.strftime('%Y%m%d-%H%M%S')}",
            created_at=now,
            repo_root=".",
            mode=mode,
            status="clean",
            findings=[],
            clusters=[],
        )
    effective_mode = mode
    if mode == "auto":
        if load_yaml(paths.config_file).get("strictness") in {"strict", "paranoid"}:
            effective_mode = "hard"
        else:
            effective_mode = "soft"

    checkpoint_time = _latest_checkpoint_time(paths)
    since = checkpoint_time or (scan.created_at if scan else now)
    changed_files = _changed_files_since(paths.root, since)
    code_changes = [path for path in changed_files if _code_like(path)]
    artifact_reference_map = _artifact_reference_map(paths, changed_files)
    active_step = _active_step(plan, session)
    allowed_paths = active_step.related_paths if active_step else []
    entrypoint_candidates = [item.paths[0] for item in scan.entrypoints[:5]] if scan else []
    decision_log = paths.decisions_log_file.read_text(encoding="utf-8", errors="ignore").lower() if paths.decisions_log_file.exists() else ""

    if changed_files:
        findings.append(
            DriftFinding(
                code="KEE-DRF-001",
                layer="session drift",
                summary="Repository changed after the latest scan",
                detail=(
                    "Files outside KEEL state directories were modified after the most recent checkpoint or scan, "
                    "so the saved flatline may no longer match repo reality."
                ),
                severity=_severity(effective_mode),
                confidence=ConfidenceLevel.INFERRED_HIGH,
                suggested_action="Run `keel scan` again or checkpoint the repo once the current step is reconciled.",
                evidence=changed_files[:8],
                teaching="Every change to the repo after a scan means your baseline picture is stale. Working from stale context is how agents build on wrong assumptions.",
            )
        )
    if _git_has_changes(paths.root):
        findings.append(
            DriftFinding(
                code="KEE-DRF-002",
                layer="session drift",
                summary="Git working tree is not clean",
                detail="Uncommitted changes can hide drift between the active plan and the current repository state.",
                severity=SeverityLevel.INFO,
                confidence=ConfidenceLevel.DETERMINISTIC,
                suggested_action="Use `keel checkpoint` before or after the next meaningful change slice.",
                evidence=[],
                teaching="Uncommitted changes are invisible to checkpoints and recovery. If drift happens now, there's no clean state to rewind to.",
            )
        )
    if paths.current_brief_file.exists() and changed_files:
        brief_mtime = datetime.fromtimestamp(paths.current_brief_file.stat().st_mtime, tz=since.tzinfo)
        newest_change = max(
            datetime.fromtimestamp((paths.root / rel).stat().st_mtime, tz=since.tzinfo)
            for rel in changed_files
            if (paths.root / rel).exists()
        )
        if newest_change > brief_mtime:
            findings.append(
                DriftFinding(
                    code="KEE-DRF-014",
                    layer="session drift",
                    summary="The current brief is stale",
                    detail="Repository changes landed after `.keel/session/current-brief.md` was last refreshed.",
                    severity=_severity(effective_mode),
                    confidence=ConfidenceLevel.DETERMINISTIC,
                    suggested_action="Refresh the current brief by running `keel plan`, `keel checkpoint`, or another state-updating command.",
                    evidence=[".keel/session/current-brief.md"] + changed_files[:5],
                    teaching="A stale brief means the agent is making decisions based on outdated context. Refresh it so the next action is grounded in reality.",
                )
            )
    if goal and goal.mode in {
        GoalMode.FIX,
        GoalMode.WIRE_UP_INCOMPLETE,
        GoalMode.EXTEND,
        GoalMode.HARDEN,
        GoalMode.ADD_FEATURE,
        GoalMode.SHIP_MVP,
    } and not deltas:
        findings.append(
            DriftFinding(
                code="KEE-DRF-003",
                layer="goal drift",
                summary="Behavior-change work has no recorded delta",
                detail="The active goal suggests behavior changes, but no delta artifact is present.",
                severity=_severity(effective_mode),
                confidence=ConfidenceLevel.INFERRED_HIGH,
                suggested_action="Run `keel delta` to record the intended change and validation mapping.",
                evidence=[goal.mode.value],
                teaching="When you change behavior without recording a delta, the done-gate can't verify the change was intentional. This is how accidental breakage ships.",
            )
        )
    if checkpoint_time is None and changed_files:
        risk_changes = [
            path
            for path in changed_files
            if _entrypoint_like(path)
            or path.endswith((".yaml", ".yml", ".toml", ".json"))
            or path.startswith("keel/specs/contracts/")
        ]
        if len(changed_files) >= 8 or risk_changes:
            findings.append(
                DriftFinding(
                    code="KEE-DRF-015",
                    layer="session drift",
                    summary="Risky change set has no checkpoint",
                    detail="A broad or high-impact change set is in flight without a recorded checkpoint snapshot.",
                    severity=SeverityLevel.WARNING if effective_mode == "soft" else SeverityLevel.BLOCKER,
                    confidence=ConfidenceLevel.INFERRED_HIGH,
                    suggested_action="Run `keel checkpoint` before proceeding further so replans and recovery stay grounded.",
                    evidence=(risk_changes or changed_files)[:8],
                    teaching="Broad changes without a checkpoint mean there's no recovery anchor. If something goes wrong, you can't get back to a known-good state.",
                )
            )
    if plan and session.active_step_id and all(
        session.active_step_id != step.step_id for phase in plan.phases for step in phase.steps
    ):
        findings.append(
            DriftFinding(
                code="KEE-DRF-004",
                layer="session drift",
                summary="Session step is no longer in the active plan",
                detail="The session points at a step that the current plan artifact does not contain.",
                severity=_severity(effective_mode),
                confidence=ConfidenceLevel.DETERMINISTIC,
                suggested_action="Run `keel next` or `keel replan` to resynchronize the active step.",
                evidence=[session.active_step_id],
                teaching="The plan says you should be on a step that no longer exists. The agent is navigating by a map that doesn't match the territory.",
            )
        )
    relevant_high_priority_questions = []
    if questions:
        for question in questions.questions:
            if question.priority.value != "high":
                continue
            if not question.related_paths or any(_path_matches(path, question.related_paths) for path in changed_files):
                relevant_high_priority_questions.append(question)
    if relevant_high_priority_questions and changed_files:
        findings.append(
            DriftFinding(
                code="KEE-DRF-005",
                layer="plan drift",
                summary="High-priority unresolved questions remain",
                detail="Implementation appears to have moved forward even though high-priority questions are still unresolved.",
                severity=_severity(effective_mode),
                confidence=ConfidenceLevel.DETERMINISTIC,
                suggested_action="Resolve the highest-priority questions or record why they are consciously deferred.",
                evidence=[question.question_id for question in relevant_high_priority_questions[:5]],
                teaching="Completing all plan steps without completing the goal means the plan was wrong or incomplete. Don't let the checklist substitute for the actual objective.",
            )
        )

    if goal and goal.mode in {GoalMode.UNDERSTAND, GoalMode.VERIFY_CLAIMS}:
        code_changes = [path for path in changed_files if _code_like(path)]
        if code_changes:
            findings.append(
                DriftFinding(
                    code="KEE-DRF-007",
                    layer="goal drift",
                    summary="Code changed during a non-implementation goal phase",
                    detail=(
                        f"The active goal is `{goal.mode.value}`, but code-like files changed after the last checkpoint or scan."
                    ),
                    severity=_severity(effective_mode),
                    confidence=ConfidenceLevel.INFERRED_HIGH,
                    suggested_action="Either capture a new implementation goal or roll the discovery session forward with a fresh plan.",
                    evidence=code_changes[:8],
                    teaching="The goal describes one thing but the code is doing another. This gap widens silently until the PR review catches it \u2014 or doesn't.",
                )
            )

    if goal and goal.mode == GoalMode.REFACTOR:
        behavior_change_signals = [
            path
            for path in changed_files
            if path.startswith("keel/specs/contracts/")
            or path.startswith("keel/specs/examples/")
            or path.startswith("keel/specs/deltas/")
        ]
        if behavior_change_signals or deltas:
            findings.append(
                DriftFinding(
                    code="KEE-DRF-008",
                    layer="goal drift",
                    summary="Refactor-only phase shows behavior-change signals",
                    detail=(
                        "Contracts, examples, or delta records changed while the active goal is `refactor-without-behavior-change`."
                    ),
                    severity=_severity(effective_mode),
                    confidence=ConfidenceLevel.INFERRED_MEDIUM,
                    suggested_action="Confirm whether behavior changed. If yes, update the goal and delta before calling the slice done.",
                    evidence=behavior_change_signals[:8] or [delta.artifact_id for delta in deltas[:4]],
                    teaching="Refactors should not change behavior. If contracts or examples changed during a refactor, something slipped that tests might not catch.",
                )
            )
    if goal and goal.mode in {
        GoalMode.FIX,
        GoalMode.WIRE_UP_INCOMPLETE,
        GoalMode.EXTEND,
        GoalMode.HARDEN,
        GoalMode.ADD_FEATURE,
        GoalMode.SHIP_MVP,
    }:
        test_changes = [path for path in changed_files if _test_like(path)]
        example_changes = [path for path in changed_files if path.startswith("keel/specs/examples/")]
        if code_changes and not test_changes and not example_changes and not goal.success_criteria:
            findings.append(
                DriftFinding(
                    code="KEE-DRF-016",
                    layer="spec drift",
                    summary="Behavior-heavy code moved without tests or acceptance updates",
                    detail="Implementation changed, but no tests, examples, or success criteria moved with it.",
                    severity=SeverityLevel.WARNING if effective_mode == "soft" else SeverityLevel.BLOCKER,
                    confidence=ConfidenceLevel.INFERRED_HIGH,
                    suggested_action="Update tests, examples, or explicit success criteria before calling this work aligned.",
                    evidence=code_changes[:8],
                    teaching="Code changed but nothing validates the change \u2014 no tests, no examples, no success criteria. This is how untested behavior ships.",
                )
            )

    if allowed_paths and changed_files:
        off_plan = [
            path
            for path in changed_files
            if not _path_matches(path, allowed_paths) and not artifact_reference_map.get(path)
        ]
        if off_plan:
            findings.append(
                DriftFinding(
                    code="KEE-DRF-009",
                    layer="plan drift",
                    summary="Recent file changes are outside the active plan step",
                    detail=(
                        f"The active plan step targets {', '.join(allowed_paths[:4])}, but unrelated files were modified "
                        "without matching an active requirement, contract, goal, or delta artifact."
                    ),
                    severity=_severity(effective_mode),
                    confidence=ConfidenceLevel.INFERRED_HIGH,
                    suggested_action="Either narrow the implementation back to the active step or replan to include the newly touched files.",
                    evidence=off_plan[:8],
                    teaching="Working outside the active plan step means scope is growing without the plan tracking it. This is the #1 way agents silently derail.",
                )
            )
    entrypoint_families = {_entrypoint_family(path) for path in entrypoint_candidates}
    if (
        scan
        and len(scan.entrypoints) > 1
        and len(entrypoint_families) > 1
        and "entrypoint" not in decision_log
        and "runtime path" not in decision_log
    ):
        findings.append(
            DriftFinding(
                code="KEE-DRF-017",
                layer="runtime-entrypoint drift",
                summary="Multiple runtime entrypoints exist without a resolved owner",
                detail="KEEL found several candidate entrypoints, but there is no recorded decision about which one governs the active path.",
                severity=SeverityLevel.WARNING if effective_mode == "soft" else SeverityLevel.BLOCKER,
                confidence=ConfidenceLevel.INFERRED_MEDIUM,
                suggested_action="Record the authoritative runtime path in a decision or checkpoint before deeper changes continue.",
                evidence=entrypoint_candidates,
            )
        )
    changed_entrypoints = [path for path in changed_files if _entrypoint_like(path)]
    if changed_entrypoints and allowed_paths and not any(_path_matches(path, allowed_paths) for path in changed_entrypoints):
        findings.append(
            DriftFinding(
                code="KEE-DRF-018",
                layer="runtime-entrypoint drift",
                summary="Entrypoint-like files changed outside the active step",
                detail="Files that look like startup or runtime entrypoints moved even though the current plan step does not target them.",
                severity=_severity(effective_mode),
                confidence=ConfidenceLevel.INFERRED_HIGH,
                suggested_action="Confirm that the active step truly includes an entrypoint change, or replan before proceeding.",
                evidence=changed_entrypoints[:8],
                teaching="Spec artifacts changed but the code didn't follow. The spec and implementation are now telling different stories.",
            )
        )

    spec_dirs = ("keel/specs/requirements/", "keel/specs/contracts/", "keel/specs/examples/")
    spec_changes = [path for path in changed_files if path.startswith(spec_dirs)]
    if spec_changes and not deltas:
        findings.append(
            DriftFinding(
                code="KEE-DRF-010",
                layer="spec drift",
                summary="Spec artifacts changed without a linked delta",
                detail="Requirements, contracts, or examples were edited, but no delta artifact records the impact.",
                severity=_severity(effective_mode),
                confidence=ConfidenceLevel.INFERRED_HIGH,
                suggested_action="Add a delta and note the requirement or contract impact before closing the phase.",
                evidence=spec_changes[:8],
                teaching="When runtime entrypoints change without the goal or plan knowing, the whole execution model might shift under you.",
            )
        )
    if (
        code_changes
        and any(directory.exists() and list(directory.glob("*")) for directory in [paths.requirements_dir, paths.contracts_dir, paths.examples_dir])
        and not spec_changes
        and not deltas
        and any(not artifact_reference_map.get(path) for path in code_changes)
    ):
        findings.append(
            DriftFinding(
                code="KEE-DRF-011",
                layer="spec drift",
                summary="Implementation moved without corresponding spec updates",
                detail="Code-like files changed while KEEL-managed requirements, contracts, or examples stayed untouched.",
                severity=SeverityLevel.WARNING if effective_mode == "soft" else SeverityLevel.BLOCKER,
                confidence=ConfidenceLevel.INFERRED_MEDIUM,
                suggested_action="Confirm whether the change should be spec-neutral. If not, update the relevant requirement, contract, example, or delta.",
                evidence=[path for path in code_changes[:8] if not artifact_reference_map.get(path)],
                teaching="Duplicate implementations are a sign that the agent lost track of existing code. This creates maintenance debt and conflicting behavior.",
            )
        )
    changed_top_level = {Path(path).parts[0] for path in changed_files if Path(path).parts}
    allowed_top_level = {Path(path).parts[0] for path in allowed_paths if Path(path).parts}
    if len(changed_top_level) >= 3 and allowed_top_level and not changed_top_level.issubset(allowed_top_level):
        findings.append(
            DriftFinding(
                code="KEE-DRF-019",
                layer="unknown-scope growth",
                summary="Touched scope is expanding beyond the planned subsystem set",
                detail="Recent edits span additional top-level areas beyond what the active step suggests.",
                severity=SeverityLevel.WARNING if effective_mode == "soft" else SeverityLevel.BLOCKER,
                confidence=ConfidenceLevel.INFERRED_MEDIUM,
                suggested_action="Pause for `keel replan` if this is becoming a subsystem-spanning change instead of a bounded slice.",
                evidence=sorted(changed_top_level)[:8],
                teaching="Touching more subsystems than planned means the blast radius is growing. Each new subsystem multiplies the chance of unintended side effects.",
            )
        )

    duplicate_candidates = []
    for changed in changed_files[:8]:
        candidate = paths.root / changed
        if not candidate.exists() or not _code_like(changed):
            continue
        basename = candidate.name
        matches = [
            str(path.relative_to(paths.root))
            for path in paths.root.rglob(basename)
            if ".keel" not in path.parts and "keel" not in path.parts[:1]
        ]
        if len(matches) >= 3:
            duplicate_candidates.append(f"{basename}: {', '.join(matches[:3])}")
    if duplicate_candidates:
        findings.append(
            DriftFinding(
                code="KEE-DRF-020",
                layer="duplicate-implementation drift",
                summary="Recent work may be creating another copy of existing logic",
                detail="The changed files share basenames with multiple existing implementations elsewhere in the repo.",
                severity=SeverityLevel.WARNING,
                confidence=ConfidenceLevel.HEURISTIC_LOW,
                suggested_action="Check whether the active change should reconcile an existing implementation instead of adding another parallel copy.",
                evidence=duplicate_candidates[:5],
            )
        )

    scope_keywords = set()
    if goal:
        for phrase in goal.scope:
            scope_keywords |= set(re.findall(r"[a-z0-9]+", phrase.lower()))
    if scope_keywords and changed_files:
        if not any(any(keyword in path.lower() for keyword in scope_keywords) for path in changed_files):
            findings.append(
                DriftFinding(
                    code="KEE-DRF-012",
                    layer="goal drift",
                    summary="Recent work does not resemble the declared scope",
                    detail="Changed file paths do not line up with the current goal scope keywords, so work may have drifted away from intent.",
                    severity=SeverityLevel.WARNING,
                    confidence=ConfidenceLevel.HEURISTIC_LOW,
                    suggested_action="Check whether the goal scope still matches the actual work or needs a focused update.",
                    evidence=changed_files[:8] + sorted(scope_keywords)[:6],
                    teaching="The work doesn't look like what was declared. Either the goal needs updating or the work needs redirecting \u2014 ignoring this gap is how projects drift.",
                )
            )

    _research_drift(changed_files, paths, goal, findings, effective_mode)
    _terminology_drift(paths, changed_files, findings, effective_mode)
    clusters = _build_clusters(
        paths=paths,
        now=now,
        findings=findings,
        changed_files=changed_files,
        effective_mode=effective_mode,
    )
    for cluster in clusters:
        findings.append(
            DriftFinding(
                code="KEE-DRF-021",
                layer=cluster.layer,
                summary=cluster.summary,
                detail=cluster.detail,
                severity=cluster.severity,
                confidence=cluster.confidence,
                suggested_action=cluster.recommended_action,
                evidence=cluster.related_codes + cluster.touched_areas,
                teaching="Repeated weak signals are a pattern, not noise. The drift detector is seeing the same problem over and over \u2014 it's time to stop and address it.",
            )
        )

    dismissed_codes = _active_dismissals(paths, now)
    if dismissed_codes:
        findings = [finding for finding in findings if finding.code not in dismissed_codes]
        if "KEE-DRF-021" in dismissed_codes:
            clusters = []

    status = "clear"
    if any(finding.severity in {SeverityLevel.ERROR, SeverityLevel.BLOCKER} for finding in findings):
        status = "blocked"
    elif findings:
        status = "warning"

    return DriftArtifact(
        artifact_id=f"drift-{now.strftime('%Y%m%d-%H%M%S')}",
        created_at=now,
        repo_root=".",
        mode=effective_mode,
        findings=findings,
        clusters=clusters,
        status=status,
    )
