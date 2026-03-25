"""Tests for drift dismissal (drift/service.py) and models layer (models/artifacts.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from keel.core.artifacts import load_yaml, save_yaml
from keel.core.paths import KeelPaths
from keel.drift.service import (
    DISMISSAL_WINDOW_MINUTES,
    MANAGED_AGENT_ROOTS,
    _active_dismissals,
    _is_managed_or_ignored_path,
    _mentions_managed,
    clear_managed_install_drift,
    dismiss_drift_codes,
)
from keel.models.artifacts import (
    AlignmentArtifact,
    AlignmentMismatch,
    ArtifactBase,
    BaselineArtifact,
    BaselineConclusion,
    ConfidenceLevel,
    DeltaArtifact,
    DriftArtifact,
    DriftCluster,
    DriftFinding,
    GoalArtifact,
    GoalMode,
    PlanArtifact,
    PlanPhase,
    PlanStep,
    PriorityLevel,
    QuestionArtifact,
    QuestionItem,
    RecoveryArtifact,
    RecoveryIssue,
    RecoveryMode,
    RecoveryStep,
    ResearchArtifact,
    ResearchFinding,
    ScanArtifact,
    ScanFinding,
    ScanItem,
    ScanStats,
    SessionState,
    SeverityLevel,
    TraceArtifact,
    TraceRow,
    ValidationArtifact,
    ValidationFinding,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_paths(tmp_path: Path) -> KeelPaths:
    paths = KeelPaths(tmp_path)
    paths.ensure()
    return paths


def _now_tz() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# dismiss_drift_codes – persistence and retrieval
# ---------------------------------------------------------------------------


class TestDismissDriftCodes:
    def test_new_dismissal_is_persisted(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)

        rows = dismiss_drift_codes(paths, codes=["KEE-DRF-001"], minutes=60)

        assert len(rows) == 1
        assert rows[0]["code"] == "KEE-DRF-001"
        assert "dismissed_at" in rows[0]
        assert "expires_at" in rows[0]

    def test_dismissed_code_survives_round_trip(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        dismiss_drift_codes(paths, codes=["KEE-DRF-002"], minutes=60)

        payload = load_yaml(paths.drift_dismissals_file)
        codes_on_disk = [d["code"] for d in payload.get("dismissals", [])]
        assert "KEE-DRF-002" in codes_on_disk

    def test_multiple_codes_dismissed_at_once(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        codes = ["KEE-DRF-003", "KEE-DRF-004", "KEE-DRF-005"]
        rows = dismiss_drift_codes(paths, codes=codes, minutes=30)

        assert len(rows) == 3
        returned_codes = {row["code"] for row in rows}
        assert returned_codes == set(codes)

    def test_re_dismissing_same_code_replaces_previous(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        dismiss_drift_codes(paths, codes=["KEE-DRF-001"], minutes=10)
        dismiss_drift_codes(paths, codes=["KEE-DRF-001"], minutes=60)

        payload = load_yaml(paths.drift_dismissals_file)
        matching = [d for d in payload.get("dismissals", []) if d["code"] == "KEE-DRF-001"]
        # There should be exactly one entry for the code (the latest one wins).
        assert len(matching) == 1

    def test_dismissal_note_is_stored(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        dismiss_drift_codes(paths, codes=["KEE-DRF-001"], note="intentional skip")

        payload = load_yaml(paths.drift_dismissals_file)
        assert payload["dismissals"][0]["note"] == "intentional skip"

    def test_expires_at_is_in_future(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        before = datetime.now().astimezone()
        dismiss_drift_codes(paths, codes=["KEE-DRF-001"], minutes=30)
        after = datetime.now().astimezone()

        payload = load_yaml(paths.drift_dismissals_file)
        expires_at = datetime.fromisoformat(payload["dismissals"][0]["expires_at"])
        expected_min = before + timedelta(minutes=30)
        expected_max = after + timedelta(minutes=30)
        assert expected_min <= expires_at <= expected_max

    def test_dismissal_removes_matching_alerts(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        save_yaml(
            paths.alerts_file,
            {
                "alerts": [
                    {"rule": "KEE-DRF-001", "msg": "test alert"},
                    {"rule": "KEE-DRF-002", "msg": "keep this"},
                ]
            },
        )
        dismiss_drift_codes(paths, codes=["KEE-DRF-001"], minutes=30)

        alerts = load_yaml(paths.alerts_file).get("alerts", [])
        rules = [a["rule"] for a in alerts]
        assert "KEE-DRF-001" not in rules
        assert "KEE-DRF-002" in rules

    def test_expired_dismissal_is_not_loaded_as_active(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        past = (_now_tz() - timedelta(hours=2)).isoformat()
        save_yaml(
            paths.drift_dismissals_file,
            {
                "dismissals": [
                    {
                        "code": "KEE-DRF-001",
                        "dismissed_at": past,
                        "expires_at": past,
                        "note": "expired",
                    }
                ]
            },
        )
        now = datetime.now().astimezone()
        active = _active_dismissals(paths, now)
        assert "KEE-DRF-001" not in active

    def test_non_expired_dismissal_is_returned_as_active(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        dismiss_drift_codes(paths, codes=["KEE-DRF-007"], minutes=60)

        now = datetime.now().astimezone()
        active = _active_dismissals(paths, now)
        assert "KEE-DRF-007" in active

    def test_expired_dismissals_are_pruned_on_load(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        past = (_now_tz() - timedelta(hours=1)).isoformat()
        future = (_now_tz() + timedelta(hours=1)).isoformat()
        save_yaml(
            paths.drift_dismissals_file,
            {
                "dismissals": [
                    {"code": "KEE-DRF-OLD", "dismissed_at": past, "expires_at": past, "note": "expired"},
                    {"code": "KEE-DRF-NEW", "dismissed_at": past, "expires_at": future, "note": "active"},
                ]
            },
        )
        now = datetime.now().astimezone()
        _active_dismissals(paths, now)

        payload = load_yaml(paths.drift_dismissals_file)
        remaining_codes = [d["code"] for d in payload.get("dismissals", [])]
        assert "KEE-DRF-OLD" not in remaining_codes
        assert "KEE-DRF-NEW" in remaining_codes

    def test_minimum_minutes_is_one(self, tmp_path: Path) -> None:
        """minutes=0 is coerced to at least 1 minute."""
        paths = _make_paths(tmp_path)
        rows = dismiss_drift_codes(paths, codes=["KEE-DRF-001"], minutes=0)
        expires_at = datetime.fromisoformat(rows[0]["expires_at"])
        dismissed_at = datetime.fromisoformat(rows[0]["dismissed_at"])
        assert expires_at > dismissed_at


# ---------------------------------------------------------------------------
# clear_managed_install_drift
# ---------------------------------------------------------------------------


class TestClearManagedInstallDrift:
    def test_removes_events_with_managed_evidence(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        save_yaml(
            paths.drift_memory_file,
            {
                "events": [
                    {
                        "seen_at": _now_tz().isoformat(),
                        "code": "KEE-DRF-001",
                        "layer": "session drift",
                        "severity": "warning",
                        "confidence": "inferred-high-confidence",
                        "summary": "managed change",
                        "evidence": [".claude/settings.json"],
                        "changed_files": [".claude/settings.json"],
                        "cluster_key": "session drift:claude",
                    }
                ],
                "cluster_emissions": {},
            },
        )
        clear_managed_install_drift(paths)

        payload = load_yaml(paths.drift_memory_file)
        assert payload["events"] == []

    def test_keeps_events_with_non_managed_evidence(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        save_yaml(
            paths.drift_memory_file,
            {
                "events": [
                    {
                        "seen_at": _now_tz().isoformat(),
                        "code": "KEE-DRF-001",
                        "layer": "session drift",
                        "severity": "warning",
                        "confidence": "inferred-high-confidence",
                        "summary": "regular change",
                        "evidence": ["src/mymodule.py"],
                        "changed_files": ["src/mymodule.py"],
                        "cluster_key": "session drift:src",
                    }
                ],
                "cluster_emissions": {},
            },
        )
        clear_managed_install_drift(paths)

        payload = load_yaml(paths.drift_memory_file)
        assert len(payload["events"]) == 1

    def test_removes_managed_cluster_emissions(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        save_yaml(
            paths.drift_memory_file,
            {
                "events": [],
                "cluster_emissions": {
                    "cluster-abc": {
                        "emitted_at": _now_tz().isoformat(),
                        "cluster_key": "session drift:.claude",
                        "related_codes": ["KEE-DRF-001"],
                        "touched_areas": [".claude"],
                    }
                },
            },
        )
        clear_managed_install_drift(paths)

        payload = load_yaml(paths.drift_memory_file)
        assert payload.get("cluster_emissions") == {}

    def test_removes_managed_alerts(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        save_yaml(
            paths.alerts_file,
            {
                "alerts": [
                    {"rule": "KEE-DRF-001", "evidence": [".codex/config.yaml"]},
                    {"rule": "KEE-DRF-002", "evidence": ["src/app.py"]},
                ]
            },
        )
        clear_managed_install_drift(paths)

        alerts = load_yaml(paths.alerts_file).get("alerts", [])
        rules = [a["rule"] for a in alerts]
        assert "KEE-DRF-001" not in rules
        assert "KEE-DRF-002" in rules

    def test_handles_missing_drift_memory_file(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        # File does not exist yet; should not raise.
        clear_managed_install_drift(paths)

    def test_handles_empty_events_and_emissions(self, tmp_path: Path) -> None:
        paths = _make_paths(tmp_path)
        save_yaml(paths.drift_memory_file, {"events": [], "cluster_emissions": {}})
        clear_managed_install_drift(paths)

        payload = load_yaml(paths.drift_memory_file)
        assert payload["events"] == []
        assert payload["cluster_emissions"] == {}


# ---------------------------------------------------------------------------
# _is_managed_or_ignored_path helper
# ---------------------------------------------------------------------------


class TestIsManagedOrIgnoredPath:
    @pytest.mark.parametrize("path", [".claude/settings.json", ".codex/foo.yaml", ".claude-plugin/init.sh"])
    def test_managed_roots_are_detected(self, path: str) -> None:
        assert _is_managed_or_ignored_path(path) is True

    @pytest.mark.parametrize("path", ["src/app.py", "tests/test_foo.py", "README.md"])
    def test_regular_paths_are_not_managed(self, path: str) -> None:
        assert _is_managed_or_ignored_path(path) is False

    def test_egg_info_suffix_is_ignored(self) -> None:
        assert _is_managed_or_ignored_path("my_package.egg-info/PKG-INFO") is True

    def test_empty_string_is_not_managed(self) -> None:
        assert _is_managed_or_ignored_path("") is False


# ---------------------------------------------------------------------------
# _mentions_managed helper
# ---------------------------------------------------------------------------


class TestMentionsManaged:
    def test_detects_managed_item_in_list(self) -> None:
        assert _mentions_managed([".claude/settings.json", "src/app.py"]) is True

    def test_returns_false_for_all_regular_items(self) -> None:
        assert _mentions_managed(["src/foo.py", "tests/bar.py"]) is False

    def test_empty_list_returns_false(self) -> None:
        assert _mentions_managed([]) is False

    def test_colon_separator_is_stripped_before_check(self) -> None:
        # Evidence items are stored as "path:detail"; only the path part matters.
        assert _mentions_managed([".codex/cfg.yaml:some detail"]) is True


# ---------------------------------------------------------------------------
# Models – Pydantic instantiation with valid data
# ---------------------------------------------------------------------------


FIXED_DT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class TestModelInstantiation:
    def test_scan_stats(self) -> None:
        stats = ScanStats(file_count=10, text_file_count=8, total_bytes=1024)
        assert stats.file_count == 10

    def test_scan_stats_defaults(self) -> None:
        stats = ScanStats()
        assert stats.file_count == 0
        assert stats.text_file_count == 0
        assert stats.total_bytes == 0

    def test_scan_item(self) -> None:
        item = ScanItem(
            name="Python",
            detail="Detected via *.py files",
            confidence=ConfidenceLevel.DETERMINISTIC,
        )
        assert item.confidence == ConfidenceLevel.DETERMINISTIC
        assert item.evidence == []
        assert item.paths == []

    def test_scan_finding(self) -> None:
        finding = ScanFinding(
            finding_id="f-001",
            category="language",
            title="Python found",
            detail="Multiple .py files.",
            confidence=ConfidenceLevel.INFERRED_HIGH,
            severity=SeverityLevel.INFO,
        )
        assert finding.severity == SeverityLevel.INFO

    def test_scan_artifact_minimal(self) -> None:
        artifact = ScanArtifact(
            artifact_id="scan-001",
            artifact_type="scan",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            stats=ScanStats(),
        )
        assert artifact.artifact_type == "scan"
        assert artifact.languages == []

    def test_goal_artifact(self) -> None:
        goal = GoalArtifact(
            artifact_id="goal-001",
            artifact_type="goal",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            mode=GoalMode.ADD_FEATURE,
            goal_statement="Add user auth",
        )
        assert goal.mode == GoalMode.ADD_FEATURE
        assert goal.scope == []

    def test_baseline_artifact(self) -> None:
        artifact = BaselineArtifact(
            artifact_id="baseline-001",
            artifact_type="baseline",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            source_scan_id="scan-001",
        )
        assert artifact.source_scan_id == "scan-001"
        assert artifact.exists_today == []

    def test_drift_finding(self) -> None:
        finding = DriftFinding(
            code="KEE-DRF-001",
            layer="session drift",
            summary="Files changed",
            detail="Details here.",
            severity=SeverityLevel.WARNING,
            confidence=ConfidenceLevel.INFERRED_HIGH,
            suggested_action="Run scan.",
        )
        assert finding.teaching is None
        assert finding.evidence == []

    def test_drift_artifact(self) -> None:
        artifact = DriftArtifact(
            artifact_id="drift-001",
            artifact_type="drift",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            mode="soft",
            status="clear",
        )
        assert artifact.findings == []
        assert artifact.clusters == []

    def test_drift_cluster(self) -> None:
        cluster = DriftCluster(
            cluster_id="cluster-abc",
            layer="session drift",
            summary="Repeated signals",
            detail="Many signals over time.",
            severity=SeverityLevel.WARNING,
            confidence=ConfidenceLevel.INFERRED_MEDIUM,
            event_count=4,
            first_seen_at=FIXED_DT.isoformat(),
            last_seen_at=FIXED_DT.isoformat(),
            recommended_action="Checkpoint now.",
        )
        assert cluster.event_count == 4
        assert cluster.related_codes == []
        assert cluster.timeline == []

    def test_session_state_defaults(self) -> None:
        state = SessionState()
        assert state.active_goal_id is None
        assert state.drift_warnings == []
        assert state.completed_step_ids == []

    def test_plan_step(self) -> None:
        step = PlanStep(
            step_id="step-01",
            title="Wire up auth",
            detail="Implement JWT.",
            done_definition="Tests pass.",
        )
        assert step.status == "pending"
        assert step.related_paths == []

    def test_plan_phase(self) -> None:
        step = PlanStep(
            step_id="step-01",
            title="Step 1",
            detail="Do it.",
            done_definition="Done.",
        )
        phase = PlanPhase(
            phase_id="phase-01",
            title="Phase 1",
            objective="Obj",
            done_definition="All steps done.",
            steps=[step],
        )
        assert len(phase.steps) == 1

    def test_plan_artifact(self) -> None:
        artifact = PlanArtifact(
            artifact_id="plan-001",
            artifact_type="plan",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            focus_area="auth",
            current_next_step="Wire up JWT",
        )
        assert artifact.phases == []

    def test_alignment_artifact(self) -> None:
        mismatch = AlignmentMismatch(
            mismatch_id="m-001",
            summary="Goal unclear",
            detail="No success criteria.",
            confidence=ConfidenceLevel.INFERRED_HIGH,
            severity=SeverityLevel.WARNING,
        )
        artifact = AlignmentArtifact(
            artifact_id="align-001",
            artifact_type="alignment",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            recommended_focus_area="auth",
            confidence_summary="medium",
            mismatches=[mismatch],
        )
        assert len(artifact.mismatches) == 1

    def test_validation_artifact(self) -> None:
        finding = ValidationFinding(
            code="KEE-VAL-001",
            message="Missing criteria",
            severity=SeverityLevel.WARNING,
            confidence=ConfidenceLevel.DETERMINISTIC,
            suggested_action="Add success criteria.",
        )
        artifact = ValidationArtifact(
            artifact_id="val-001",
            artifact_type="validation",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            findings=[finding],
            status="warning",
        )
        assert artifact.status == "warning"
        assert len(artifact.findings) == 1

    def test_question_artifact(self) -> None:
        item = QuestionItem(
            question_id="q-001",
            question="What is the runtime path?",
            why_it_matters="Needed for correct config.",
            triggered_by="scan",
            unblocks="planning",
            priority=PriorityLevel.HIGH,
            confidence=ConfidenceLevel.DETERMINISTIC,
        )
        artifact = QuestionArtifact(
            artifact_id="q-artifact-001",
            artifact_type="questions",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            questions=[item],
        )
        assert artifact.questions[0].priority == PriorityLevel.HIGH

    def test_research_artifact(self) -> None:
        finding = ResearchFinding(
            finding_id="rf-001",
            source="web",
            source_type="url",
            source_trust="low",
            trust_rank=3,
            title="Some paper",
            summary="Summary here.",
            status="unverified",
            citation="http://example.com",
            confidence=ConfidenceLevel.HEURISTIC_LOW,
        )
        artifact = ResearchArtifact(
            artifact_id="research-001",
            artifact_type="research",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            enabled=False,
            findings=[finding],
        )
        assert artifact.enabled is False

    def test_trace_artifact(self) -> None:
        row = TraceRow(
            row_id="tr-001",
            goal_reference="goal-001",
            validation_reference="val-001",
            status="passing",
        )
        artifact = TraceArtifact(
            artifact_id="trace-001",
            artifact_type="trace",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            rows=[row],
        )
        assert len(artifact.rows) == 1
        assert row.plan_step_ids == []

    def test_delta_artifact(self) -> None:
        artifact = DeltaArtifact(
            artifact_id="delta-001",
            artifact_type="delta",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            summary="Added auth module",
        )
        assert artifact.impacted_paths == []
        assert artifact.acceptance_criteria == []

    def test_recovery_artifact(self) -> None:
        issue = RecoveryIssue(
            issue_id="ri-001",
            kind="drift",
            summary="State diverged",
            detail="Details.",
            severity=SeverityLevel.ERROR,
            confidence=ConfidenceLevel.INFERRED_HIGH,
        )
        mode = RecoveryMode(
            mode_id="rm-001",
            label="replan",
            summary="Replan from checkpoint.",
            confidence=ConfidenceLevel.INFERRED_HIGH,
        )
        step = RecoveryStep(
            step_id="rs-001",
            title="Run keel replan",
            detail="Execute replan command.",
        )
        artifact = RecoveryArtifact(
            artifact_id="recovery-001",
            artifact_type="recovery",
            created_at=FIXED_DT,
            repo_root="/tmp/repo",
            divergence_at=FIXED_DT.isoformat(),
            divergence_reason="Unexpected file changes",
            recommended_mode="replan",
            recovery_confidence=ConfidenceLevel.INFERRED_MEDIUM,
            brief_path=".keel/session/current-brief.md",
            issues=[issue],
            recovery_modes=[mode],
            steps=[step],
        )
        assert artifact.divergence_reason == "Unexpected file changes"
        assert artifact.intent_replay == {}


# ---------------------------------------------------------------------------
# Models – validation with invalid / missing required fields
# ---------------------------------------------------------------------------


class TestModelValidation:
    def test_artifact_base_requires_artifact_id(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactBase(
                artifact_type="scan",
                created_at=FIXED_DT,
                repo_root="/tmp",
            )  # type: ignore[call-arg]

    def test_artifact_base_requires_created_at(self) -> None:
        with pytest.raises(ValidationError):
            ArtifactBase(
                artifact_id="x",
                artifact_type="scan",
                repo_root="/tmp",
            )  # type: ignore[call-arg]

    def test_goal_artifact_requires_mode(self) -> None:
        with pytest.raises(ValidationError):
            GoalArtifact(
                artifact_id="g-001",
                artifact_type="goal",
                created_at=FIXED_DT,
                repo_root="/tmp",
                goal_statement="Do something",
                # mode is missing
            )  # type: ignore[call-arg]

    def test_goal_artifact_rejects_invalid_mode(self) -> None:
        with pytest.raises(ValidationError):
            GoalArtifact(
                artifact_id="g-001",
                artifact_type="goal",
                created_at=FIXED_DT,
                repo_root="/tmp",
                mode="not-a-real-mode",
                goal_statement="Do something",
            )

    def test_scan_finding_rejects_invalid_severity(self) -> None:
        with pytest.raises(ValidationError):
            ScanFinding(
                finding_id="f-001",
                category="lang",
                title="T",
                detail="D",
                confidence=ConfidenceLevel.DETERMINISTIC,
                severity="critical",  # not a valid SeverityLevel
            )

    def test_drift_finding_requires_code(self) -> None:
        with pytest.raises(ValidationError):
            DriftFinding(
                layer="session drift",
                summary="x",
                detail="y",
                severity=SeverityLevel.WARNING,
                confidence=ConfidenceLevel.DETERMINISTIC,
                suggested_action="z",
            )  # type: ignore[call-arg]

    def test_plan_step_requires_done_definition(self) -> None:
        with pytest.raises(ValidationError):
            PlanStep(
                step_id="s-1",
                title="T",
                detail="D",
            )  # type: ignore[call-arg]

    def test_alignment_artifact_requires_recommended_focus_area(self) -> None:
        with pytest.raises(ValidationError):
            AlignmentArtifact(
                artifact_id="a-001",
                artifact_type="alignment",
                created_at=FIXED_DT,
                repo_root="/tmp",
                confidence_summary="medium",
                # recommended_focus_area missing
            )  # type: ignore[call-arg]

    def test_baseline_artifact_requires_source_scan_id(self) -> None:
        with pytest.raises(ValidationError):
            BaselineArtifact(
                artifact_id="b-001",
                artifact_type="baseline",
                created_at=FIXED_DT,
                repo_root="/tmp",
            )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Models – Enum completeness
# ---------------------------------------------------------------------------


class TestEnumCompleteness:
    def test_goal_mode_has_all_expected_values(self) -> None:
        expected = {
            "understand",
            "debug",
            "fix",
            "wire-up-incomplete-code",
            "extend",
            "refactor-without-behavior-change",
            "harden",
            "add-feature",
            "ship-mvp",
            "clean-up-drift",
            "verify-implementation-claims",
        }
        actual = {member.value for member in GoalMode}
        assert actual == expected

    def test_severity_level_has_all_expected_values(self) -> None:
        expected = {"info", "warning", "error", "blocker"}
        actual = {member.value for member in SeverityLevel}
        assert actual == expected

    def test_confidence_level_has_all_expected_values(self) -> None:
        expected = {
            "deterministic",
            "inferred-high-confidence",
            "inferred-medium-confidence",
            "heuristic-low-confidence",
            "unresolved",
        }
        actual = {member.value for member in ConfidenceLevel}
        assert actual == expected

    def test_priority_level_has_all_expected_values(self) -> None:
        expected = {"low", "medium", "high"}
        actual = {member.value for member in PriorityLevel}
        assert actual == expected

    def test_goal_mode_values_are_strings(self) -> None:
        for member in GoalMode:
            assert isinstance(member.value, str)

    def test_severity_level_str_mixin(self) -> None:
        # SeverityLevel inherits str so members compare equal to their values.
        assert SeverityLevel.WARNING == "warning"
        assert SeverityLevel.BLOCKER == "blocker"

    def test_confidence_level_str_mixin(self) -> None:
        assert ConfidenceLevel.DETERMINISTIC == "deterministic"
        assert ConfidenceLevel.UNRESOLVED == "unresolved"


# ---------------------------------------------------------------------------
# Models – serialization round-trips (model_dump / model_validate)
# ---------------------------------------------------------------------------


class TestSerializationRoundTrips:
    def _round_trip(self, model: object) -> object:
        cls = type(model)
        data = model.model_dump(mode="json")  # type: ignore[attr-defined]
        return cls.model_validate(data)

    def test_scan_artifact_round_trip(self) -> None:
        original = ScanArtifact(
            artifact_id="scan-rt-001",
            artifact_type="scan",
            created_at=FIXED_DT,
            repo_root="/tmp",
            stats=ScanStats(file_count=5, text_file_count=4, total_bytes=512),
            languages=[
                ScanItem(
                    name="Python",
                    detail="Detected",
                    confidence=ConfidenceLevel.DETERMINISTIC,
                    paths=["src/main.py"],
                )
            ],
        )
        recovered = self._round_trip(original)
        assert recovered.artifact_id == original.artifact_id
        assert recovered.stats.file_count == 5
        assert recovered.languages[0].name == "Python"

    def test_goal_artifact_round_trip(self) -> None:
        original = GoalArtifact(
            artifact_id="goal-rt-001",
            artifact_type="goal",
            created_at=FIXED_DT,
            repo_root="/tmp",
            mode=GoalMode.UNDERSTAND,
            goal_statement="Understand the codebase",
            scope=["src/"],
            success_criteria=["All modules mapped"],
        )
        recovered = self._round_trip(original)
        assert recovered.mode == GoalMode.UNDERSTAND
        assert recovered.scope == ["src/"]
        assert recovered.success_criteria == ["All modules mapped"]

    def test_drift_artifact_round_trip(self) -> None:
        finding = DriftFinding(
            code="KEE-DRF-001",
            layer="session drift",
            summary="Files changed",
            detail="Details.",
            severity=SeverityLevel.WARNING,
            confidence=ConfidenceLevel.INFERRED_HIGH,
            suggested_action="Re-scan.",
            evidence=["src/app.py"],
        )
        original = DriftArtifact(
            artifact_id="drift-rt-001",
            artifact_type="drift",
            created_at=FIXED_DT,
            repo_root="/tmp",
            mode="hard",
            findings=[finding],
            status="warning",
        )
        recovered = self._round_trip(original)
        assert len(recovered.findings) == 1
        assert recovered.findings[0].code == "KEE-DRF-001"
        assert recovered.mode == "hard"

    def test_session_state_round_trip(self) -> None:
        original = SessionState(
            active_goal_id="goal-001",
            active_step_id="step-01",
            completed_step_ids=["step-00"],
            drift_warnings=["KEE-DRF-001"],
        )
        recovered = self._round_trip(original)
        assert recovered.active_goal_id == "goal-001"
        assert recovered.completed_step_ids == ["step-00"]
        assert recovered.drift_warnings == ["KEE-DRF-001"]

    def test_plan_artifact_round_trip(self) -> None:
        step = PlanStep(
            step_id="step-01",
            title="Wire up auth",
            detail="Implement JWT.",
            done_definition="Tests pass.",
            related_paths=["src/auth/"],
        )
        phase = PlanPhase(
            phase_id="phase-01",
            title="Auth phase",
            objective="Obj",
            done_definition="Done.",
            steps=[step],
        )
        original = PlanArtifact(
            artifact_id="plan-rt-001",
            artifact_type="plan",
            created_at=FIXED_DT,
            repo_root="/tmp",
            focus_area="auth",
            phases=[phase],
            current_next_step="Wire up JWT",
        )
        recovered = self._round_trip(original)
        assert len(recovered.phases) == 1
        assert recovered.phases[0].steps[0].step_id == "step-01"
        assert recovered.phases[0].steps[0].related_paths == ["src/auth/"]

    def test_validation_artifact_round_trip(self) -> None:
        finding = ValidationFinding(
            code="KEE-VAL-001",
            message="Missing criteria",
            severity=SeverityLevel.ERROR,
            confidence=ConfidenceLevel.DETERMINISTIC,
            suggested_action="Add success criteria.",
            paths=["keel/discovery/goals/goal-001.yaml"],
        )
        original = ValidationArtifact(
            artifact_id="val-rt-001",
            artifact_type="validation",
            created_at=FIXED_DT,
            repo_root="/tmp",
            findings=[finding],
            status="blocked",
        )
        recovered = self._round_trip(original)
        assert recovered.status == "blocked"
        assert recovered.findings[0].severity == SeverityLevel.ERROR
        assert recovered.findings[0].paths == ["keel/discovery/goals/goal-001.yaml"]

    def test_baseline_conclusion_round_trip(self) -> None:
        conclusion = BaselineConclusion(
            conclusion_id="bc-001",
            category="language",
            title="Python",
            detail="Detected Python.",
            confidence=ConfidenceLevel.INFERRED_HIGH,
            evidence=["src/main.py"],
            paths=["src/"],
        )
        data = conclusion.model_dump(mode="json")
        recovered = BaselineConclusion.model_validate(data)
        assert recovered.conclusion_id == "bc-001"
        assert recovered.paths == ["src/"]

    def test_model_dump_excludes_none_by_default(self) -> None:
        finding = DriftFinding(
            code="KEE-DRF-001",
            layer="session drift",
            summary="x",
            detail="y",
            severity=SeverityLevel.INFO,
            confidence=ConfidenceLevel.DETERMINISTIC,
            suggested_action="z",
            # teaching is None (optional)
        )
        data = finding.model_dump(mode="json", exclude_none=True)
        assert "teaching" not in data

    def test_model_dump_includes_none_without_exclusion(self) -> None:
        finding = DriftFinding(
            code="KEE-DRF-001",
            layer="session drift",
            summary="x",
            detail="y",
            severity=SeverityLevel.INFO,
            confidence=ConfidenceLevel.DETERMINISTIC,
            suggested_action="z",
        )
        data = finding.model_dump(mode="json")
        assert "teaching" in data
        assert data["teaching"] is None
