"""Tests for SessionService (session/service.py) and alert helpers (session/alerts.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from keel.core.paths import KeelPaths
from keel.models.artifacts import (
    AlignmentArtifact,
    BaselineArtifact,
    BaselineConclusion,
    ConfidenceLevel,
    DriftArtifact,
    DriftFinding,
    GoalArtifact,
    GoalMode,
    PlanArtifact,
    PlanPhase,
    PlanStep,
    PriorityLevel,
    QuestionArtifact,
    QuestionItem,
    ResearchArtifact,
    ResearchFinding,
    ScanArtifact,
    ScanStats,
    SessionState,
    SeverityLevel,
    ValidationArtifact,
    ValidationFinding,
)
from keel.session.alerts import ALERT_WINDOW_MINUTES, load_active_alerts, update_alert_feed
from keel.session.service import SessionService


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
REPO_ROOT = "/repo"


@pytest.fixture()
def paths(tmp_path: Path) -> KeelPaths:
    p = KeelPaths(tmp_path)
    p.ensure()
    return p


@pytest.fixture()
def svc(paths: KeelPaths) -> SessionService:
    return SessionService(paths)


@pytest.fixture()
def empty_session() -> SessionState:
    return SessionState()


def _make_scan(artifact_id: str = "scan-001") -> ScanArtifact:
    return ScanArtifact(
        artifact_id=artifact_id,
        artifact_type="scan",
        created_at=NOW,
        repo_root=REPO_ROOT,
        stats=ScanStats(file_count=5, text_file_count=5, total_bytes=1024),
    )


def _make_baseline(artifact_id: str = "baseline-001") -> BaselineArtifact:
    return BaselineArtifact(
        artifact_id=artifact_id,
        artifact_type="baseline",
        created_at=NOW,
        repo_root=REPO_ROOT,
        source_scan_id="scan-001",
    )


def _make_goal(artifact_id: str = "goal-001") -> GoalArtifact:
    return GoalArtifact(
        artifact_id=artifact_id,
        artifact_type="goal",
        created_at=NOW,
        repo_root=REPO_ROOT,
        mode=GoalMode.UNDERSTAND,
        goal_statement="Map the runtime path",
        constraints=["no network calls", "keep tests green"],
        out_of_scope=["UI changes", "database migrations"],
    )


def _make_alignment(artifact_id: str = "align-001") -> AlignmentArtifact:
    return AlignmentArtifact(
        artifact_id=artifact_id,
        artifact_type="alignment",
        created_at=NOW,
        repo_root=REPO_ROOT,
        recommended_focus_area="finish scan layer",
        confidence_summary="high",
    )


def _make_plan(
    artifact_id: str = "plan-001",
    phases: list[PlanPhase] | None = None,
) -> PlanArtifact:
    if phases is None:
        phases = [
            PlanPhase(
                phase_id="phase-1",
                title="Phase 1",
                objective="Baseline",
                done_definition="baseline done",
                steps=[
                    PlanStep(
                        step_id="step-1",
                        title="Run scan",
                        detail="Scan the repo",
                        done_definition="scan complete",
                    ),
                    PlanStep(
                        step_id="step-2",
                        title="Write baseline",
                        detail="Record findings",
                        done_definition="baseline written",
                    ),
                ],
            )
        ]
    return PlanArtifact(
        artifact_id=artifact_id,
        artifact_type="plan",
        created_at=NOW,
        repo_root=REPO_ROOT,
        focus_area="discovery",
        phases=phases,
        current_next_step="Run scan",
    )


def _make_questions(artifact_id: str = "q-001") -> QuestionArtifact:
    return QuestionArtifact(
        artifact_id=artifact_id,
        artifact_type="questions",
        created_at=NOW,
        repo_root=REPO_ROOT,
        questions=[
            QuestionItem(
                question_id="Q-1",
                question="Is the service stateless?",
                why_it_matters="affects caching",
                triggered_by="scan",
                unblocks="design",
                priority=PriorityLevel.HIGH,
                confidence=ConfidenceLevel.INFERRED_HIGH,
            ),
        ],
    )


def _make_research(artifact_id: str = "res-001", status: str = "active") -> ResearchArtifact:
    finding = ResearchFinding(
        finding_id="rf-1",
        source="docs",
        source_type="local",
        source_trust="trusted",
        trust_rank=1,
        title="Key finding",
        summary="Something important",
        status="active",
        citation="docs/overview.md",
        confidence=ConfidenceLevel.DETERMINISTIC,
    )
    return ResearchArtifact(
        artifact_id=artifact_id,
        artifact_type="research",
        created_at=NOW,
        repo_root=REPO_ROOT,
        enabled=True,
        status=status,
        findings=[finding],
    )


def _make_drift_artifact(artifact_id: str = "drift-001", severity: SeverityLevel = SeverityLevel.WARNING) -> DriftArtifact:
    finding = DriftFinding(
        code="KEE-DRF-001",
        layer="session",
        summary="test drift finding",
        detail="detail here",
        severity=severity,
        confidence=ConfidenceLevel.INFERRED_HIGH,
        suggested_action="fix it",
        evidence=["src/foo.py"],
    )
    return DriftArtifact(
        artifact_id=artifact_id,
        artifact_type="drift",
        created_at=NOW,
        repo_root=REPO_ROOT,
        mode="hard",
        findings=[finding],
        status="ok",
    )


def _make_validation_artifact(artifact_id: str = "val-001", severity: SeverityLevel = SeverityLevel.WARNING) -> ValidationArtifact:
    finding = ValidationFinding(
        code="KEE-VAL-001",
        message="test validation finding",
        severity=severity,
        confidence=ConfidenceLevel.DETERMINISTIC,
        suggested_action="resolve it",
        paths=["src/bar.py"],
    )
    return ValidationArtifact(
        artifact_id=artifact_id,
        artifact_type="validation",
        created_at=NOW,
        repo_root=REPO_ROOT,
        findings=[finding],
        status="ok",
    )


# ===========================================================================
# SessionService.load()
# ===========================================================================

class TestLoad:
    def test_load_returns_empty_session_when_file_missing(self, svc: SessionService) -> None:
        session = svc.load()
        assert isinstance(session, SessionState)
        assert session.active_goal_id is None

    def test_load_returns_session_from_yaml(self, svc: SessionService, paths: KeelPaths) -> None:
        payload = {"active_goal_id": "goal-abc", "active_plan_id": "plan-xyz"}
        paths.current_file.write_text(yaml.safe_dump(payload), encoding="utf-8")

        session = svc.load()
        assert session.active_goal_id == "goal-abc"
        assert session.active_plan_id == "plan-xyz"

    def test_load_handles_partial_yaml(self, svc: SessionService, paths: KeelPaths) -> None:
        # Only some fields present; unset fields get defaults.
        paths.current_file.write_text(yaml.safe_dump({"active_goal_id": "g-1"}), encoding="utf-8")
        session = svc.load()
        assert session.active_goal_id == "g-1"
        assert session.completed_step_ids == []


# ===========================================================================
# SessionService.save()
# ===========================================================================

class TestSave:
    def test_save_writes_yaml_to_current_file(self, svc: SessionService, paths: KeelPaths) -> None:
        session = SessionState(active_goal_id="goal-save-1")
        svc.save(session)
        assert paths.current_file.exists()
        raw = yaml.safe_load(paths.current_file.read_text(encoding="utf-8"))
        assert raw["active_goal_id"] == "goal-save-1"

    def test_save_returns_the_session_unchanged(self, svc: SessionService) -> None:
        session = SessionState(active_goal_id="goal-roundtrip")
        returned = svc.save(session)
        assert returned is session

    def test_save_excludes_none_fields(self, svc: SessionService, paths: KeelPaths) -> None:
        svc.save(SessionState())
        raw = yaml.safe_load(paths.current_file.read_text(encoding="utf-8")) or {}
        # None-valued fields like active_goal_id must not appear in the file.
        assert "active_goal_id" not in raw


# ===========================================================================
# SessionService.load_decisions()
# ===========================================================================

class TestLoadDecisions:
    def test_returns_empty_list_when_file_missing(self, svc: SessionService) -> None:
        assert svc.load_decisions() == []

    def test_returns_decisions_stripped_of_timestamp(self, svc: SessionService, paths: KeelPaths) -> None:
        paths.decisions_log_file.write_text(
            "2026-03-25T10:00:00+00:00 Use pydantic v2\n"
            "2026-03-25T10:01:00+00:00 Prefer YAML over JSON\n",
            encoding="utf-8",
        )
        decisions = svc.load_decisions()
        assert "Use pydantic v2" in decisions
        assert "Prefer YAML over JSON" in decisions

    def test_limit_is_respected(self, svc: SessionService, paths: KeelPaths) -> None:
        lines = "\n".join(
            f"2026-03-25T00:0{i}:00+00:00 Decision {i}" for i in range(8)
        ) + "\n"
        paths.decisions_log_file.write_text(lines, encoding="utf-8")
        decisions = svc.load_decisions(limit=3)
        assert len(decisions) <= 3

    def test_deduplication_removes_repeated_messages(self, svc: SessionService, paths: KeelPaths) -> None:
        paths.decisions_log_file.write_text(
            "2026-03-25T10:00:00+00:00 Same decision\n"
            "2026-03-25T10:01:00+00:00 Same decision\n",
            encoding="utf-8",
        )
        decisions = svc.load_decisions()
        assert decisions.count("Same decision") == 1

    def test_skips_blank_lines(self, svc: SessionService, paths: KeelPaths) -> None:
        paths.decisions_log_file.write_text(
            "\n2026-03-25T10:00:00+00:00 Valid decision\n\n",
            encoding="utf-8",
        )
        decisions = svc.load_decisions()
        assert decisions == ["Valid decision"]


# ===========================================================================
# SessionService.load_unresolved_questions()
# ===========================================================================

class TestLoadUnresolvedQuestions:
    def test_returns_empty_list_when_file_missing(self, svc: SessionService) -> None:
        result = svc.load_unresolved_questions()
        assert result == []

    def test_returns_questions_list(self, svc: SessionService, paths: KeelPaths) -> None:
        payload = {"questions": [{"question_id": "Q-1", "question": "Is it safe?"}]}
        paths.unresolved_questions_file.write_text(yaml.safe_dump(payload), encoding="utf-8")
        result = svc.load_unresolved_questions()
        assert len(result) == 1
        assert result[0]["question_id"] == "Q-1"

    def test_returns_empty_list_when_questions_key_absent(self, svc: SessionService, paths: KeelPaths) -> None:
        paths.unresolved_questions_file.write_text(yaml.safe_dump({}), encoding="utf-8")
        assert svc.load_unresolved_questions() == []


# ===========================================================================
# SessionService.sync_questions()
# ===========================================================================

class TestSyncQuestions:
    def test_writes_questions_yaml(self, svc: SessionService, paths: KeelPaths) -> None:
        session = SessionState()
        questions = _make_questions()
        svc.sync_questions(session, questions)

        raw = yaml.safe_load(paths.unresolved_questions_file.read_text(encoding="utf-8"))
        assert len(raw["questions"]) == 1
        assert raw["questions"][0]["question_id"] == "Q-1"

    def test_updates_session_question_ids(self, svc: SessionService) -> None:
        session = SessionState()
        questions = _make_questions()
        updated = svc.sync_questions(session, questions)
        assert "Q-1" in updated.unresolved_question_ids

    def test_empty_questions_clears_ids(self, svc: SessionService) -> None:
        session = SessionState(unresolved_question_ids=["Q-old"])
        empty_q = QuestionArtifact(
            artifact_id="q-empty",
            artifact_type="questions",
            created_at=NOW,
            repo_root=REPO_ROOT,
            questions=[],
        )
        updated = svc.sync_questions(session, empty_q)
        assert updated.unresolved_question_ids == []


# ===========================================================================
# SessionService.update_from_start_flow()
# ===========================================================================

class TestUpdateFromStartFlow:
    def _run(self, svc: SessionService, *, research: ResearchArtifact | None = None) -> SessionState:
        session = SessionState()
        return svc.update_from_start_flow(
            session,
            scan=_make_scan(),
            baseline=_make_baseline(),
            goal=_make_goal(),
            research=research,
            questions=_make_questions(),
            alignment=_make_alignment(),
            plan=_make_plan(),
        )

    def test_sets_artifact_ids_on_session(self, svc: SessionService) -> None:
        updated = self._run(svc)
        assert updated.active_goal_id == "goal-001"
        assert updated.latest_scan_id == "scan-001"
        assert updated.latest_baseline_id == "baseline-001"
        assert updated.active_plan_id == "plan-001"
        assert updated.latest_alignment_id == "align-001"

    def test_sets_first_phase_and_step(self, svc: SessionService) -> None:
        updated = self._run(svc)
        assert updated.active_phase_id == "phase-1"
        assert updated.active_step_id == "step-1"

    def test_active_research_id_recorded(self, svc: SessionService) -> None:
        updated = self._run(svc, research=_make_research(status="active"))
        assert "res-001" in updated.research_artifact_ids

    def test_disabled_research_not_recorded(self, svc: SessionService) -> None:
        updated = self._run(svc, research=_make_research(status="disabled"))
        assert updated.research_artifact_ids == []

    def test_none_research_not_recorded(self, svc: SessionService) -> None:
        updated = self._run(svc, research=None)
        assert updated.research_artifact_ids == []

    def test_question_ids_synced(self, svc: SessionService) -> None:
        updated = self._run(svc)
        assert "Q-1" in updated.unresolved_question_ids

    def test_plan_with_no_phases_leaves_step_none(self, svc: SessionService) -> None:
        session = SessionState()
        empty_plan = _make_plan(phases=[])
        updated = svc.update_from_start_flow(
            session,
            scan=_make_scan(),
            baseline=_make_baseline(),
            goal=_make_goal(),
            research=None,
            questions=_make_questions(),
            alignment=_make_alignment(),
            plan=empty_plan,
        )
        assert updated.active_phase_id is None
        assert updated.active_step_id is None


# ===========================================================================
# SessionService.write_current_brief()
# ===========================================================================

class TestWriteCurrentBrief:
    def _write(
        self,
        svc: SessionService,
        *,
        goal: GoalArtifact | None = _make_goal(),
        plan: PlanArtifact | None = _make_plan(),
        baseline: BaselineArtifact | None = None,
        alignment: AlignmentArtifact | None = _make_alignment(),
        research: ResearchArtifact | None = None,
        unresolved_questions: list[str] | None = None,
        decisions: list[str] | None = None,
        blockers: list[str] | None = None,
        must_not_change: list[str] | None = None,
    ) -> str:
        path = svc.write_current_brief(
            goal=goal,
            plan=plan,
            baseline=baseline,
            alignment=alignment,
            research=research,
            unresolved_questions=unresolved_questions or [],
            decisions=decisions or [],
            blockers=blockers,
            must_not_change=must_not_change,
        )
        return path.read_text(encoding="utf-8")

    def test_returns_path_to_brief_file(self, svc: SessionService, paths: KeelPaths) -> None:
        path = svc.write_current_brief(
            goal=_make_goal(),
            plan=_make_plan(),
            baseline=None,
            alignment=_make_alignment(),
            research=None,
            unresolved_questions=[],
            decisions=[],
        )
        assert path == paths.current_brief_file

    def test_brief_contains_goal_statement(self, svc: SessionService) -> None:
        text = self._write(svc)
        assert "Map the runtime path" in text

    def test_brief_contains_phase_title(self, svc: SessionService) -> None:
        text = self._write(svc)
        assert "Phase 1" in text

    def test_brief_contains_next_step(self, svc: SessionService) -> None:
        text = self._write(svc)
        assert "Run scan" in text

    def test_brief_no_goal_shows_not_set(self, svc: SessionService) -> None:
        text = self._write(svc, goal=None, alignment=None)
        assert "not set" in text

    def test_brief_no_plan_shows_not_set(self, svc: SessionService) -> None:
        text = self._write(svc, plan=None)
        assert "not set" in text

    def test_brief_shows_unresolved_questions(self, svc: SessionService) -> None:
        text = self._write(svc, unresolved_questions=["Q: Is it safe?"])
        assert "Q: Is it safe?" in text

    def test_brief_shows_decisions(self, svc: SessionService) -> None:
        text = self._write(svc, decisions=["Use pydantic v2"])
        assert "Use pydantic v2" in text

    def test_brief_shows_blockers(self, svc: SessionService) -> None:
        text = self._write(svc, blockers=["CI is broken"])
        assert "CI is broken" in text

    def test_brief_shows_none_recorded_when_empty(self, svc: SessionService) -> None:
        text = self._write(svc, blockers=None)
        assert "none recorded" in text

    def test_brief_shows_research_findings(self, svc: SessionService) -> None:
        text = self._write(svc, research=_make_research())
        assert "Key finding" in text

    def test_brief_shows_offline_when_no_research(self, svc: SessionService) -> None:
        text = self._write(svc, research=None)
        assert "offline" in text

    def test_brief_includes_baseline_facts(self, svc: SessionService) -> None:
        baseline = _make_baseline()
        baseline.exists_today = [
            BaselineConclusion(
                conclusion_id="c-1",
                category="test",
                title="Entry point found",
                detail="",
                confidence=ConfidenceLevel.DETERMINISTIC,
            )
        ]
        text = self._write(svc, baseline=baseline)
        assert "Entry point found" in text

    def test_brief_shows_repo_not_summarized_when_no_baseline(self, svc: SessionService) -> None:
        text = self._write(svc, baseline=None)
        assert "repo state not summarized yet" in text

    def test_brief_shows_alignment_focus_area_as_done_condition(self, svc: SessionService) -> None:
        text = self._write(svc)
        assert "finish scan layer" in text

    def test_must_not_change_overrides_invariants(self, svc: SessionService) -> None:
        text = self._write(svc, must_not_change=["Do not touch the DB schema"])
        assert "Do not touch the DB schema" in text

    def test_invariants_fall_back_to_goal_fields(self, svc: SessionService) -> None:
        text = self._write(svc, must_not_change=None)
        # goal.out_of_scope and goal.constraints are used
        assert any(
            item in text
            for item in ["UI changes", "database migrations", "no network calls", "keep tests green"]
        )


# ===========================================================================
# SessionService.record_decision()
# ===========================================================================

class TestRecordDecision:
    def test_appends_decision_to_log_file(self, svc: SessionService, paths: KeelPaths) -> None:
        session = SessionState()
        svc.record_decision(session, "Adopt hexagonal architecture")
        text = paths.decisions_log_file.read_text(encoding="utf-8")
        assert "Adopt hexagonal architecture" in text

    def test_multiple_decisions_are_all_recorded(self, svc: SessionService, paths: KeelPaths) -> None:
        session = SessionState()
        svc.record_decision(session, "Decision A")
        svc.record_decision(session, "Decision B")
        text = paths.decisions_log_file.read_text(encoding="utf-8")
        assert "Decision A" in text
        assert "Decision B" in text

    def test_updates_latest_decisions_on_session(self, svc: SessionService) -> None:
        session = SessionState()
        updated = svc.record_decision(session, "Important call")
        assert "Important call" in updated.latest_decisions

    def test_duplicate_decision_deduplicated_in_session(self, svc: SessionService) -> None:
        session = SessionState()
        svc.record_decision(session, "Repeated")
        updated = svc.record_decision(session, "Repeated")
        assert updated.latest_decisions.count("Repeated") == 1


# ===========================================================================
# SessionService.advance_step()
# ===========================================================================

class TestAdvanceStep:
    def test_marks_current_step_as_completed(self, svc: SessionService) -> None:
        session = SessionState(active_step_id="step-1")
        plan = _make_plan()
        updated, _ = svc.advance_step(session, plan)
        assert "step-1" in updated.completed_step_ids

    def test_moves_to_next_uncompleted_step(self, svc: SessionService) -> None:
        session = SessionState(active_step_id="step-1")
        plan = _make_plan()
        updated, message = svc.advance_step(session, plan)
        assert updated.active_step_id == "step-2"
        assert "step-2" in message.lower() or "Write baseline".lower() in message.lower()

    def test_all_steps_complete_message(self, svc: SessionService) -> None:
        session = SessionState(active_step_id="step-2", completed_step_ids=["step-1"])
        plan = _make_plan()
        updated, message = svc.advance_step(session, plan)
        assert updated.active_step_id is None
        assert "complete" in message.lower()

    def test_no_phases_returns_no_phases_message(self, svc: SessionService) -> None:
        session = SessionState()
        plan = _make_plan(phases=[])
        _, message = svc.advance_step(session, plan)
        assert "No plan phases" in message

    def test_does_not_duplicate_completed_step_on_repeat(self, svc: SessionService) -> None:
        session = SessionState(active_step_id="step-1", completed_step_ids=["step-1"])
        plan = _make_plan()
        updated, _ = svc.advance_step(session, plan)
        assert updated.completed_step_ids.count("step-1") == 1

    def test_advances_phase_id(self, svc: SessionService) -> None:
        phase2 = PlanPhase(
            phase_id="phase-2",
            title="Phase 2",
            objective="Extend",
            done_definition="done",
            steps=[
                PlanStep(
                    step_id="step-3",
                    title="Ship it",
                    detail="Deploy",
                    done_definition="deployed",
                )
            ],
        )
        plan = _make_plan(
            phases=[
                PlanPhase(
                    phase_id="phase-1",
                    title="Phase 1",
                    objective="Baseline",
                    done_definition="done",
                    steps=[
                        PlanStep(
                            step_id="step-1",
                            title="Run scan",
                            detail="Scan",
                            done_definition="scanned",
                        )
                    ],
                ),
                phase2,
            ]
        )
        session = SessionState(active_step_id="step-1", active_phase_id="phase-1")
        updated, _ = svc.advance_step(session, plan)
        assert updated.active_step_id == "step-3"
        assert updated.active_phase_id == "phase-2"


# ===========================================================================
# SessionService.add_checkpoint()
# ===========================================================================

class TestAddCheckpoint:
    def test_creates_checkpoints_file(self, svc: SessionService, paths: KeelPaths) -> None:
        session = SessionState(active_goal_id="goal-001")
        svc.add_checkpoint("initial state captured", session)
        assert paths.checkpoints_file.exists()

    def test_checkpoint_contains_note(self, svc: SessionService, paths: KeelPaths) -> None:
        session = SessionState()
        svc.add_checkpoint("step 1 done", session)
        raw = yaml.safe_load(paths.checkpoints_file.read_text(encoding="utf-8"))
        assert any(cp["note"] == "step 1 done" for cp in raw["checkpoints"])

    def test_checkpoint_default_kind_is_manual(self, svc: SessionService, paths: KeelPaths) -> None:
        svc.add_checkpoint("manual note", SessionState())
        raw = yaml.safe_load(paths.checkpoints_file.read_text(encoding="utf-8"))
        assert raw["checkpoints"][0]["kind"] == "manual"

    def test_checkpoint_kind_can_be_overridden(self, svc: SessionService, paths: KeelPaths) -> None:
        svc.add_checkpoint("auto note", SessionState(), kind="auto")
        raw = yaml.safe_load(paths.checkpoints_file.read_text(encoding="utf-8"))
        assert raw["checkpoints"][0]["kind"] == "auto"

    def test_multiple_checkpoints_accumulate(self, svc: SessionService, paths: KeelPaths) -> None:
        session = SessionState()
        svc.add_checkpoint("first", session)
        svc.add_checkpoint("second", session)
        raw = yaml.safe_load(paths.checkpoints_file.read_text(encoding="utf-8"))
        assert len(raw["checkpoints"]) == 2

    def test_checkpoint_records_active_ids(self, svc: SessionService, paths: KeelPaths) -> None:
        session = SessionState(
            active_goal_id="goal-007",
            active_plan_id="plan-007",
            active_step_id="step-007",
        )
        svc.add_checkpoint("state snapshot", session)
        raw = yaml.safe_load(paths.checkpoints_file.read_text(encoding="utf-8"))
        cp = raw["checkpoints"][0]
        assert cp["active_goal_id"] == "goal-007"
        assert cp["active_plan_id"] == "plan-007"
        assert cp["active_step_id"] == "step-007"


# ===========================================================================
# load_active_alerts()
# ===========================================================================

class TestLoadActiveAlerts:
    def test_returns_empty_list_when_file_missing(self, paths: KeelPaths) -> None:
        result = load_active_alerts(paths)
        assert result == []

    def test_returns_alert_within_window(self, paths: KeelPaths) -> None:
        recent = datetime.now().astimezone().isoformat()
        payload = {
            "alerts": [
                {
                    "alert_id": "ALT-abc",
                    "key": "abc",
                    "source": "drift",
                    "summary": "recent alert",
                    "last_seen_at": recent,
                }
            ]
        }
        paths.alerts_file.write_text(yaml.safe_dump(payload), encoding="utf-8")
        result = load_active_alerts(paths)
        assert len(result) == 1
        assert result[0]["summary"] == "recent alert"

    def test_filters_out_old_alerts(self, paths: KeelPaths) -> None:
        old_time = (
            datetime.now().astimezone() - timedelta(minutes=ALERT_WINDOW_MINUTES + 5)
        ).isoformat()
        payload = {
            "alerts": [
                {
                    "alert_id": "ALT-old",
                    "key": "old",
                    "source": "drift",
                    "summary": "stale alert",
                    "last_seen_at": old_time,
                }
            ]
        }
        paths.alerts_file.write_text(yaml.safe_dump(payload), encoding="utf-8")
        result = load_active_alerts(paths)
        assert result == []

    def test_handles_invalid_timestamp_gracefully(self, paths: KeelPaths) -> None:
        payload = {
            "alerts": [
                {
                    "alert_id": "ALT-bad",
                    "key": "bad",
                    "source": "drift",
                    "summary": "bad ts",
                    "last_seen_at": "not-a-date",
                }
            ]
        }
        paths.alerts_file.write_text(yaml.safe_dump(payload), encoding="utf-8")
        # The source falls back to `cutoff` for invalid timestamps, and since
        # `last_seen >= cutoff` uses >=, the alert sits exactly on the boundary
        # and is therefore included rather than filtered.
        result = load_active_alerts(paths)
        assert len(result) == 1
        assert result[0]["summary"] == "bad ts"

    def test_respects_limit(self, paths: KeelPaths) -> None:
        recent = datetime.now().astimezone().isoformat()
        alerts = [
            {"alert_id": f"ALT-{i}", "key": str(i), "source": "drift", "summary": f"alert {i}", "last_seen_at": recent}
            for i in range(10)
        ]
        paths.alerts_file.write_text(yaml.safe_dump({"alerts": alerts}), encoding="utf-8")
        result = load_active_alerts(paths, limit=3)
        assert len(result) == 3

    def test_missing_last_seen_at_treated_as_boundary(self, paths: KeelPaths) -> None:
        # The source sets last_seen = cutoff when the field is absent, so
        # `last_seen >= cutoff` is True and the alert is included.
        payload = {
            "alerts": [
                {"alert_id": "ALT-nots", "key": "nots", "source": "drift", "summary": "no ts"}
            ]
        }
        paths.alerts_file.write_text(yaml.safe_dump(payload), encoding="utf-8")
        result = load_active_alerts(paths)
        assert len(result) == 1
        assert result[0]["summary"] == "no ts"


# ===========================================================================
# update_alert_feed()
# ===========================================================================

class TestUpdateAlertFeed:
    def test_drift_finding_creates_alert(self, paths: KeelPaths) -> None:
        drift = _make_drift_artifact()
        validation = ValidationArtifact(
            artifact_id="val-empty",
            artifact_type="validation",
            created_at=NOW,
            repo_root=REPO_ROOT,
            findings=[],
            status="ok",
        )
        result = update_alert_feed(paths=paths, drift=drift, validation=validation)
        assert len(result) >= 1
        assert any(a["source"] == "drift" for a in result)

    def test_validation_warning_creates_alert(self, paths: KeelPaths) -> None:
        drift = DriftArtifact(
            artifact_id="drift-empty",
            artifact_type="drift",
            created_at=NOW,
            repo_root=REPO_ROOT,
            mode="hard",
            findings=[],
            status="ok",
        )
        validation = _make_validation_artifact(severity=SeverityLevel.WARNING)
        result = update_alert_feed(paths=paths, drift=drift, validation=validation)
        assert any(a["source"] == "validation" for a in result)

    def test_info_drift_findings_are_skipped(self, paths: KeelPaths) -> None:
        drift = _make_drift_artifact(severity=SeverityLevel.INFO)
        validation = ValidationArtifact(
            artifact_id="val-empty2",
            artifact_type="validation",
            created_at=NOW,
            repo_root=REPO_ROOT,
            findings=[],
            status="ok",
        )
        result = update_alert_feed(paths=paths, drift=drift, validation=validation)
        assert result == []

    def test_info_validation_findings_are_skipped(self, paths: KeelPaths) -> None:
        drift = DriftArtifact(
            artifact_id="drift-empty2",
            artifact_type="drift",
            created_at=NOW,
            repo_root=REPO_ROOT,
            mode="hard",
            findings=[],
            status="ok",
        )
        validation = _make_validation_artifact(severity=SeverityLevel.INFO)
        result = update_alert_feed(paths=paths, drift=drift, validation=validation)
        assert result == []

    def test_duplicate_drift_finding_increments_count(self, paths: KeelPaths) -> None:
        drift = _make_drift_artifact()
        validation = ValidationArtifact(
            artifact_id="val-empty3",
            artifact_type="validation",
            created_at=NOW,
            repo_root=REPO_ROOT,
            findings=[],
            status="ok",
        )
        update_alert_feed(paths=paths, drift=drift, validation=validation)
        update_alert_feed(paths=paths, drift=drift, validation=validation)

        raw = yaml.safe_load(paths.alerts_file.read_text(encoding="utf-8"))
        drift_alerts = [a for a in raw["alerts"] if a.get("source") == "drift"]
        assert len(drift_alerts) == 1
        assert drift_alerts[0]["count"] == 2

    def test_duplicate_validation_finding_increments_count(self, paths: KeelPaths) -> None:
        drift = DriftArtifact(
            artifact_id="drift-empty3",
            artifact_type="drift",
            created_at=NOW,
            repo_root=REPO_ROOT,
            mode="hard",
            findings=[],
            status="ok",
        )
        validation = _make_validation_artifact(severity=SeverityLevel.ERROR)
        update_alert_feed(paths=paths, drift=drift, validation=validation)
        update_alert_feed(paths=paths, drift=drift, validation=validation)

        raw = yaml.safe_load(paths.alerts_file.read_text(encoding="utf-8"))
        val_alerts = [a for a in raw["alerts"] if a.get("source") == "validation"]
        assert val_alerts[0]["count"] == 2

    def test_alert_id_prefixed_with_ALT(self, paths: KeelPaths) -> None:
        drift = _make_drift_artifact()
        validation = ValidationArtifact(
            artifact_id="val-empty4",
            artifact_type="validation",
            created_at=NOW,
            repo_root=REPO_ROOT,
            findings=[],
            status="ok",
        )
        update_alert_feed(paths=paths, drift=drift, validation=validation)
        raw = yaml.safe_load(paths.alerts_file.read_text(encoding="utf-8"))
        for alert in raw["alerts"]:
            assert alert["alert_id"].startswith("ALT-")

    def test_persists_alerts_to_file(self, paths: KeelPaths) -> None:
        drift = _make_drift_artifact()
        validation = ValidationArtifact(
            artifact_id="val-empty5",
            artifact_type="validation",
            created_at=NOW,
            repo_root=REPO_ROOT,
            findings=[],
            status="ok",
        )
        update_alert_feed(paths=paths, drift=drift, validation=validation)
        assert paths.alerts_file.exists()

    def test_teaching_field_included_when_present(self, paths: KeelPaths) -> None:
        finding = DriftFinding(
            code="KEE-DRF-T",
            layer="session",
            summary="finding with teaching",
            detail="detail",
            severity=SeverityLevel.WARNING,
            confidence=ConfidenceLevel.DETERMINISTIC,
            suggested_action="fix",
            teaching="Here is some teaching text",
        )
        drift = DriftArtifact(
            artifact_id="drift-teach",
            artifact_type="drift",
            created_at=NOW,
            repo_root=REPO_ROOT,
            mode="hard",
            findings=[finding],
            status="ok",
        )
        validation = ValidationArtifact(
            artifact_id="val-empty6",
            artifact_type="validation",
            created_at=NOW,
            repo_root=REPO_ROOT,
            findings=[],
            status="ok",
        )
        update_alert_feed(paths=paths, drift=drift, validation=validation)
        raw = yaml.safe_load(paths.alerts_file.read_text(encoding="utf-8"))
        assert raw["alerts"][0]["teaching"] == "Here is some teaching text"

    def test_blocker_validation_finding_creates_alert(self, paths: KeelPaths) -> None:
        drift = DriftArtifact(
            artifact_id="drift-empty4",
            artifact_type="drift",
            created_at=NOW,
            repo_root=REPO_ROOT,
            mode="hard",
            findings=[],
            status="ok",
        )
        validation = _make_validation_artifact(severity=SeverityLevel.BLOCKER)
        result = update_alert_feed(paths=paths, drift=drift, validation=validation)
        assert any(a["severity"] == "blocker" for a in result)
