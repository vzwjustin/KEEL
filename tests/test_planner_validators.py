"""Tests for planner/service.py and validators/service.py."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest

from keel.config import KeelConfig, StrictnessProfile
from keel.core.paths import KeelPaths
from keel.models.artifacts import (
    AlignmentArtifact,
    AlignmentMismatch,
    BaselineArtifact,
    BaselineConclusion,
    ConfidenceLevel,
    DeltaArtifact,
    GoalArtifact,
    GoalMode,
    PlanArtifact,
    PriorityLevel,
    QuestionArtifact,
    QuestionItem,
    ScanArtifact,
    ScanItem,
    ScanStats,
    SeverityLevel,
)
from keel.planner.service import build_plan
from keel.validators.service import run_validation


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 25, 12, 0, 0).astimezone()
_REPO = "/tmp/test-repo"


def _scan_item(name: str, paths: Optional[list[str]] = None) -> ScanItem:
    return ScanItem(
        name=name,
        detail=f"{name} detail",
        confidence=ConfidenceLevel.INFERRED_HIGH,
        paths=paths or [],
    )


def _minimal_scan() -> ScanArtifact:
    return ScanArtifact(
        artifact_id="scan-001",
        artifact_type="scan",
        created_at=_NOW,
        repo_root=_REPO,
        stats=ScanStats(file_count=10, text_file_count=8, total_bytes=4096),
        entrypoints=[_scan_item("main.py", ["main.py"])],
        modules=[_scan_item("core", ["src/core.py"])],
        configs=[_scan_item("pyproject.toml", ["pyproject.toml"])],
    )


def _rich_scan() -> ScanArtifact:
    return ScanArtifact(
        artifact_id="scan-002",
        artifact_type="scan",
        created_at=_NOW,
        repo_root=_REPO,
        stats=ScanStats(file_count=50, text_file_count=40, total_bytes=102400),
        entrypoints=[
            _scan_item("main.py", ["main.py"]),
            _scan_item("app.py", ["app.py"]),
        ],
        modules=[
            _scan_item("auth", ["src/auth.py"]),
            _scan_item("db", ["src/db.py"]),
            _scan_item("api", ["src/api.py"]),
        ],
        tests=[_scan_item("test_core", ["tests/test_core.py"])],
        configs=[_scan_item("pyproject.toml", ["pyproject.toml"])],
    )


def _goal(
    mode: GoalMode,
    statement: str = "Test goal",
    success_criteria: Optional[list[str]] = None,
    scope: Optional[list[str]] = None,
    constraints: Optional[list[str]] = None,
) -> GoalArtifact:
    return GoalArtifact(
        artifact_id="goal-001",
        artifact_type="goal",
        created_at=_NOW,
        repo_root=_REPO,
        mode=mode,
        goal_statement=statement,
        success_criteria=success_criteria or [],
        scope=scope or [],
        constraints=constraints or [],
    )


def _alignment(mismatches: Optional[list[AlignmentMismatch]] = None) -> AlignmentArtifact:
    return AlignmentArtifact(
        artifact_id="align-001",
        artifact_type="alignment",
        created_at=_NOW,
        repo_root=_REPO,
        mismatches=mismatches or [],
        recommended_focus_area="Start with the core module.",
        confidence_summary="High confidence.",
    )


def _question_artifact(priority: PriorityLevel = PriorityLevel.MEDIUM) -> QuestionArtifact:
    return QuestionArtifact(
        artifact_id="q-001",
        artifact_type="questions",
        created_at=_NOW,
        repo_root=_REPO,
        questions=[
            QuestionItem(
                question_id="Q1",
                question="What is the primary entrypoint?",
                why_it_matters="Needed to scope the change.",
                triggered_by="scan",
                unblocks="planning",
                priority=priority,
                confidence=ConfidenceLevel.INFERRED_HIGH,
            )
        ],
    )


def _baseline_with_unknowns() -> BaselineArtifact:
    return BaselineArtifact(
        artifact_id="base-001",
        artifact_type="baseline",
        created_at=_NOW,
        repo_root=_REPO,
        source_scan_id="scan-001",
        unknowns=[
            BaselineConclusion(
                conclusion_id="U1",
                category="unknown",
                title="Entry path unclear",
                detail="Multiple potential entrypoints detected.",
                confidence=ConfidenceLevel.HEURISTIC_LOW,
                paths=["main.py", "app.py"],
            )
        ],
    )


def _plan_artifact() -> PlanArtifact:
    """Minimal PlanArtifact for use as a validator input."""
    from keel.models.artifacts import PlanPhase, PlanStep

    step = PlanStep(
        step_id="PH1-STEP1",
        title="Confirm source of truth",
        detail="Verify the entrypoint.",
        done_definition="Entrypoint is known.",
    )
    phase = PlanPhase(
        phase_id="PHASE-1",
        title="Lock Reality",
        objective="Reduce ambiguity.",
        done_definition="Facts are solid.",
        steps=[step],
    )
    return PlanArtifact(
        artifact_id="plan-001",
        artifact_type="plan",
        created_at=_NOW,
        repo_root=_REPO,
        focus_area="Core module",
        phases=[phase],
        current_next_step=step.title,
    )


def _delta_artifact() -> DeltaArtifact:
    return DeltaArtifact(
        artifact_id="delta-001",
        artifact_type="delta",
        created_at=_NOW,
        repo_root=_REPO,
        summary="Add feature X",
        impacted_paths=["src/feature.py"],
        acceptance_criteria=["Feature X passes all tests"],
        validation_mapping=["test_feature_x"],
    )


def _paths(tmp_path: Path) -> KeelPaths:
    p = KeelPaths(tmp_path)
    p.ensure()
    return p


# ===========================================================================
# Planner tests
# ===========================================================================

class TestBuildPlanOutputStructure:
    """build_plan() always returns a PlanArtifact with exactly 4 phases."""

    def _assert_base_structure(self, plan: PlanArtifact) -> None:
        assert isinstance(plan, PlanArtifact)
        assert plan.artifact_type == "plan"
        assert plan.artifact_id.startswith("plan-")
        assert plan.repo_root == _REPO
        assert len(plan.phases) == 4
        for phase in plan.phases:
            assert len(phase.steps) >= 1, f"Phase {phase.phase_id} has no steps"
        assert plan.current_next_step != ""
        assert plan.focus_area != ""

    def test_understand_mode(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.UNDERSTAND),
            alignment=None,
            questions=None,
        )
        self._assert_base_structure(plan)
        assert plan.phases[1].title == "Map Reality"

    def test_verify_claims_mode(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(
                GoalMode.VERIFY_CLAIMS,
                success_criteria=["API returns 200", "Schema is valid"],
            ),
            alignment=None,
            questions=None,
        )
        self._assert_base_structure(plan)
        assert plan.phases[1].title == "Map Reality"
        # VERIFY_CLAIMS with criteria should generate a second phase-2 step
        ph2_step_ids = [s.step_id for s in plan.phases[1].steps]
        assert "PH2-STEP2" in ph2_step_ids

    def test_fix_mode(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.FIX, scope=["src/broken.py"]),
            alignment=None,
            questions=None,
        )
        self._assert_base_structure(plan)
        assert plan.phases[1].title == "Shape The Change"
        assert plan.phases[1].objective == "Locate and scope the fix within the identified files."

    def test_add_feature_mode(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_rich_scan(),
            baseline=None,
            goal=_goal(
                GoalMode.ADD_FEATURE,
                success_criteria=["Users can register", "Token is issued"],
                scope=["src/auth.py"],
            ),
            alignment=_alignment(),
            questions=None,
        )
        self._assert_base_structure(plan)
        assert plan.phases[1].title == "Shape The Change"
        # ADD_FEATURE always produces at least 2 phase-2 steps
        assert len(plan.phases[1].steps) >= 2

    def test_refactor_mode(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.REFACTOR, scope=["src/core.py"]),
            alignment=None,
            questions=None,
        )
        self._assert_base_structure(plan)
        assert plan.phases[1].title == "Shape The Change"
        assert "contracts" in plan.phases[1].steps[0].title.lower()

    def test_harden_mode(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_rich_scan(),
            baseline=None,
            goal=_goal(GoalMode.HARDEN),
            alignment=None,
            questions=None,
        )
        self._assert_base_structure(plan)
        assert plan.phases[1].title == "Shape The Change"
        assert "coverage" in plan.phases[1].objective.lower()

    def test_ship_mvp_mode(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.SHIP_MVP),
            alignment=None,
            questions=None,
        )
        self._assert_base_structure(plan)
        assert plan.phases[1].title == "Shape The Change"

    def test_clean_up_drift_mode_falls_through_to_generic(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.CLEAN_UP_DRIFT),
            alignment=None,
            questions=None,
        )
        self._assert_base_structure(plan)
        assert plan.phases[1].title == "Shape The Change"


class TestBuildPlanPhaseStructure:
    """Phase IDs, titles, and step IDs are structurally sound."""

    def test_phase_ids_are_canonical(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.UNDERSTAND),
            alignment=None,
            questions=None,
        )
        ids = [ph.phase_id for ph in plan.phases]
        assert ids == ["PHASE-1", "PHASE-2", "PHASE-3", "PHASE-4"]

    def test_phase_titles_for_understand(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.UNDERSTAND),
            alignment=None,
            questions=None,
        )
        titles = [ph.title for ph in plan.phases]
        assert titles[0] == "Lock Reality"
        assert titles[1] == "Map Reality"
        assert titles[2] == "Execute"
        assert titles[3] == "Reconcile"

    def test_phase_titles_for_fix(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.FIX),
            alignment=None,
            questions=None,
        )
        titles = [ph.title for ph in plan.phases]
        assert titles[1] == "Shape The Change"

    def test_step_ids_are_unique_within_phases(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_rich_scan(),
            baseline=_baseline_with_unknowns(),
            goal=_goal(
                GoalMode.ADD_FEATURE,
                success_criteria=["Crit A", "Crit B", "Crit C"],
            ),
            alignment=_alignment(),
            questions=_question_artifact(),
        )
        for phase in plan.phases:
            step_ids = [s.step_id for s in phase.steps]
            assert len(step_ids) == len(set(step_ids)), (
                f"Duplicate step IDs in {phase.phase_id}: {step_ids}"
            )

    def test_all_steps_have_done_definitions(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_rich_scan(),
            baseline=_baseline_with_unknowns(),
            goal=_goal(GoalMode.FIX, success_criteria=["Fix the bug"]),
            alignment=_alignment(),
            questions=None,
        )
        for phase in plan.phases:
            for step in phase.steps:
                assert step.done_definition, (
                    f"Step {step.step_id} in {phase.phase_id} has empty done_definition"
                )


class TestBuildPlanMinimalVsRichContext:
    """Minimal context (all None) still produces a valid plan; rich context adds more steps."""

    def test_all_none_inputs_produces_valid_plan(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=None,
            baseline=None,
            goal=None,
            alignment=None,
            questions=None,
        )
        assert isinstance(plan, PlanArtifact)
        assert len(plan.phases) == 4
        # Phase 1 fallback step exists
        assert plan.phases[0].steps[0].title == "Confirm the current source of truth"
        # No alignment: focus_area falls back to default string
        assert "highest-confidence" in plan.focus_area

    def test_no_goal_defaults_to_understand_mode(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=None,
            alignment=None,
            questions=None,
        )
        assert plan.phases[1].title == "Map Reality"

    def test_baseline_unknowns_inject_ph1_resolution_steps(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=_baseline_with_unknowns(),
            goal=_goal(GoalMode.FIX),
            alignment=None,
            questions=None,
        )
        ph1_titles = [s.title for s in plan.phases[0].steps]
        assert any("Resolve" in t for t in ph1_titles)

    def test_open_questions_add_ph1_step(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.FIX),
            alignment=None,
            questions=_question_artifact(),
        )
        ph1_titles = [s.title for s in plan.phases[0].steps]
        assert any("open questions" in t.lower() for t in ph1_titles)

    def test_multiple_entrypoints_add_ph1_step(self) -> None:
        plan = build_plan(
            repo_root=_REPO,
            scan=_rich_scan(),  # has 2 entrypoints
            baseline=None,
            goal=_goal(GoalMode.UNDERSTAND),
            alignment=None,
            questions=None,
        )
        ph1_titles = [s.title for s in plan.phases[0].steps]
        assert any("entrypoint" in t.lower() for t in ph1_titles)

    def test_no_tests_in_scan_adds_ph1_coverage_step(self) -> None:
        scan_no_tests = ScanArtifact(
            artifact_id="scan-nt",
            artifact_type="scan",
            created_at=_NOW,
            repo_root=_REPO,
            stats=ScanStats(file_count=5),
            entrypoints=[_scan_item("main.py", ["main.py"])],
            # tests list intentionally left empty
        )
        plan = build_plan(
            repo_root=_REPO,
            scan=scan_no_tests,
            baseline=None,
            goal=_goal(GoalMode.FIX),
            alignment=None,
            questions=None,
        )
        ph1_titles = [s.title for s in plan.phases[0].steps]
        assert any("test" in t.lower() for t in ph1_titles)

    def test_success_criteria_drive_ph3_execution_steps(self) -> None:
        criteria = ["Crit A", "Crit B", "Crit C"]
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.FIX, success_criteria=criteria),
            alignment=None,
            questions=None,
        )
        ph3_step_ids = [s.step_id for s in plan.phases[2].steps]
        # One step per criterion (max 3) plus the validate step
        assert "PH3-STEP1" in ph3_step_ids
        assert "PH3-STEP2" in ph3_step_ids
        assert "PH3-STEP3" in ph3_step_ids

    def test_alignment_mismatches_inject_ph4_verify_steps(self) -> None:
        mismatch = AlignmentMismatch(
            mismatch_id="M1",
            summary="Goal and plan are out of sync",
            detail="Plan steps do not map to goal criteria.",
            confidence=ConfidenceLevel.INFERRED_HIGH,
            severity=SeverityLevel.WARNING,
        )
        plan = build_plan(
            repo_root=_REPO,
            scan=_minimal_scan(),
            baseline=None,
            goal=_goal(GoalMode.EXTEND),
            alignment=_alignment(mismatches=[mismatch]),
            questions=None,
        )
        ph4_titles = [s.title for s in plan.phases[3].steps]
        assert any("Verify resolved" in t for t in ph4_titles)

    def test_alignment_focus_area_is_used(self) -> None:
        align = _alignment()
        align_focus = align.recommended_focus_area
        plan = build_plan(
            repo_root=_REPO,
            scan=None,
            baseline=None,
            goal=_goal(GoalMode.UNDERSTAND),
            alignment=align,
            questions=None,
        )
        assert plan.focus_area == align_focus

    def test_rich_context_produces_more_ph1_steps_than_minimal(self) -> None:
        minimal_plan = build_plan(
            repo_root=_REPO,
            scan=None,
            baseline=None,
            goal=None,
            alignment=None,
            questions=None,
        )
        rich_plan = build_plan(
            repo_root=_REPO,
            scan=_rich_scan(),
            baseline=_baseline_with_unknowns(),
            goal=_goal(GoalMode.FIX),
            alignment=None,
            questions=_question_artifact(),
        )
        assert len(rich_plan.phases[0].steps) > len(minimal_plan.phases[0].steps)


# ===========================================================================
# Validator tests
# ===========================================================================

class TestRunValidationCleanPass:
    """No findings when all required artifacts are present and healthy."""

    def test_clean_pass_with_goal_plan_no_questions(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(
            GoalMode.UNDERSTAND,
            success_criteria=["Understand the architecture"],
        )
        plan = _plan_artifact()
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=plan,
            questions=None,
        )
        assert result.status == "ok"
        assert result.findings == []

    def test_clean_pass_behavior_mode_with_delta(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(
            GoalMode.FIX,
            success_criteria=["Bug is fixed"],
        )
        plan = _plan_artifact()
        delta = _delta_artifact()
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=plan,
            questions=None,
            deltas=[delta],
        )
        assert result.status == "ok"
        assert result.findings == []


class TestValidationFindingKEEVAL001:
    """KEE-VAL-001: active goal has no success criteria."""

    def test_goal_without_success_criteria_triggers_001(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=[])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-001" in codes

    def test_001_severity_is_error(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.FIX, success_criteria=[])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=[_delta_artifact()],
        )
        finding = next(f for f in result.findings if f.code == "KEE-VAL-001")
        assert finding.severity == SeverityLevel.ERROR

    def test_001_not_raised_when_no_goal(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=None,
            plan=_plan_artifact(),
            questions=None,
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-001" not in codes

    def test_001_not_raised_when_criteria_present(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=["Criterion A"])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-001" not in codes


class TestValidationFindingKEEVAL002:
    """KEE-VAL-002: no active plan exists."""

    def test_no_plan_triggers_002(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=["Understand"])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=None,
            questions=None,
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-002" in codes

    def test_002_severity_is_error(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=None,
            plan=None,
            questions=None,
        )
        finding = next(f for f in result.findings if f.code == "KEE-VAL-002")
        assert finding.severity == SeverityLevel.ERROR

    def test_002_not_raised_when_plan_present(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=["Understand"])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-002" not in codes


class TestValidationFindingKEEVAL003:
    """KEE-VAL-003: behavior-changing goal without a linked delta artifact."""

    @pytest.mark.parametrize("mode", [
        GoalMode.FIX,
        GoalMode.WIRE_UP_INCOMPLETE,
        GoalMode.EXTEND,
        GoalMode.HARDEN,
        GoalMode.ADD_FEATURE,
        GoalMode.SHIP_MVP,
    ])
    def test_behavior_mode_without_delta_triggers_003(
        self, tmp_path: Path, mode: GoalMode
    ) -> None:
        paths = _paths(tmp_path)
        goal = _goal(mode, success_criteria=["Some criterion"])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=[],
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-003" in codes

    def test_003_not_raised_for_understand_mode(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=["Understand the codebase"])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=[],
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-003" not in codes

    def test_003_not_raised_when_delta_present(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.FIX, success_criteria=["Fix bug"])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=[_delta_artifact()],
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-003" not in codes

    def test_003_severity_warning_on_standard_profile(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.FIX, success_criteria=["Fix bug"])
        config = KeelConfig(strictness=StrictnessProfile.STANDARD)
        result = run_validation(
            paths=paths,
            config=config,
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=[],
        )
        finding = next(f for f in result.findings if f.code == "KEE-VAL-003")
        assert finding.severity == SeverityLevel.WARNING

    def test_003_severity_escalates_to_error_on_strict_profile(
        self, tmp_path: Path
    ) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.FIX, success_criteria=["Fix bug"])
        config = KeelConfig(strictness=StrictnessProfile.STRICT)
        result = run_validation(
            paths=paths,
            config=config,
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=[],
        )
        finding = next(f for f in result.findings if f.code == "KEE-VAL-003")
        assert finding.severity == SeverityLevel.ERROR

    def test_003_severity_escalates_to_blocker_on_paranoid_profile(
        self, tmp_path: Path
    ) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.ADD_FEATURE, success_criteria=["Feature works"])
        config = KeelConfig(strictness=StrictnessProfile.PARANOID)
        result = run_validation(
            paths=paths,
            config=config,
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=[],
        )
        finding = next(f for f in result.findings if f.code == "KEE-VAL-003")
        assert finding.severity == SeverityLevel.BLOCKER


class TestValidationFindingKEEVAL004:
    """KEE-VAL-004: high-priority unresolved questions remain."""

    def test_high_priority_question_triggers_004(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        questions = _question_artifact(priority=PriorityLevel.HIGH)
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=["Understand"])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=questions,
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-004" in codes

    def test_medium_priority_question_does_not_trigger_004(
        self, tmp_path: Path
    ) -> None:
        paths = _paths(tmp_path)
        questions = _question_artifact(priority=PriorityLevel.MEDIUM)
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=["Understand"])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=questions,
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-004" not in codes

    def test_low_priority_question_does_not_trigger_004(
        self, tmp_path: Path
    ) -> None:
        paths = _paths(tmp_path)
        questions = _question_artifact(priority=PriorityLevel.LOW)
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=["Understand"])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=questions,
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-004" not in codes

    def test_004_severity_warning_on_standard_profile(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        questions = _question_artifact(priority=PriorityLevel.HIGH)
        config = KeelConfig(strictness=StrictnessProfile.STANDARD)
        result = run_validation(
            paths=paths,
            config=config,
            goal=_goal(GoalMode.UNDERSTAND, success_criteria=["x"]),
            plan=_plan_artifact(),
            questions=questions,
        )
        finding = next(f for f in result.findings if f.code == "KEE-VAL-004")
        assert finding.severity == SeverityLevel.WARNING

    def test_004_severity_escalates_to_error_on_strict_profile(
        self, tmp_path: Path
    ) -> None:
        paths = _paths(tmp_path)
        questions = _question_artifact(priority=PriorityLevel.HIGH)
        config = KeelConfig(strictness=StrictnessProfile.STRICT)
        result = run_validation(
            paths=paths,
            config=config,
            goal=_goal(GoalMode.UNDERSTAND, success_criteria=["x"]),
            plan=_plan_artifact(),
            questions=questions,
        )
        finding = next(f for f in result.findings if f.code == "KEE-VAL-004")
        assert finding.severity == SeverityLevel.ERROR

    def test_004_severity_escalates_to_blocker_on_paranoid_profile(
        self, tmp_path: Path
    ) -> None:
        paths = _paths(tmp_path)
        questions = _question_artifact(priority=PriorityLevel.HIGH)
        config = KeelConfig(strictness=StrictnessProfile.PARANOID)
        result = run_validation(
            paths=paths,
            config=config,
            goal=_goal(GoalMode.UNDERSTAND, success_criteria=["x"]),
            plan=_plan_artifact(),
            questions=questions,
        )
        finding = next(f for f in result.findings if f.code == "KEE-VAL-004")
        assert finding.severity == SeverityLevel.BLOCKER


class TestValidationStatusRollup:
    """Overall status field reflects the worst-case finding severity."""

    def test_status_ok_when_no_findings(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=["Understand"])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
        )
        assert result.status == "ok"

    def test_status_warning_when_only_warnings(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        # KEE-VAL-003 at STANDARD strictness is a WARNING
        goal = _goal(GoalMode.FIX, success_criteria=["Fix"])
        config = KeelConfig(strictness=StrictnessProfile.STANDARD)
        result = run_validation(
            paths=paths,
            config=config,
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=[],
        )
        assert result.status == "warning"

    def test_status_error_when_error_finding_present(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        # KEE-VAL-001 always produces an ERROR
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=[])
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
        )
        assert result.status == "error"

    def test_status_error_when_blocker_finding_present(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.FIX, success_criteria=["Fix"])
        config = KeelConfig(strictness=StrictnessProfile.PARANOID)
        result = run_validation(
            paths=paths,
            config=config,
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=[],
        )
        assert result.status == "error"


class TestValidationEdgeCases:
    """Edge cases: missing artifacts, empty goal, paths in findings."""

    def test_all_none_inputs_produces_only_002(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=None,
            plan=None,
            questions=None,
        )
        # Only KEE-VAL-002 (no plan) should fire; no goal => no 001, no 003
        codes = [f.code for f in result.findings]
        assert codes == ["KEE-VAL-002"]

    def test_finding_paths_reference_keel_directories(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=None,
            plan=None,
            questions=None,
        )
        finding_002 = next(f for f in result.findings if f.code == "KEE-VAL-002")
        assert any(str(paths.plans_dir) in p for p in finding_002.paths)

    def test_artifact_id_and_repo_root_are_set(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=None,
            plan=None,
            questions=None,
        )
        assert result.artifact_id.startswith("validation-")
        assert result.artifact_type == "validation"
        assert result.repo_root == str(paths.root)

    def test_deltas_none_treated_same_as_empty_list(self, tmp_path: Path) -> None:
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.FIX, success_criteria=["Fix"])
        result_none = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=None,
        )
        result_empty = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=_plan_artifact(),
            questions=None,
            deltas=[],
        )
        codes_none = {f.code for f in result_none.findings}
        codes_empty = {f.code for f in result_empty.findings}
        assert codes_none == codes_empty

    def test_multiple_findings_accumulate(self, tmp_path: Path) -> None:
        """Goal with no criteria, no plan, and a high-priority question triggers 3 findings."""
        paths = _paths(tmp_path)
        goal = _goal(GoalMode.UNDERSTAND, success_criteria=[])
        questions = _question_artifact(priority=PriorityLevel.HIGH)
        result = run_validation(
            paths=paths,
            config=KeelConfig(),
            goal=goal,
            plan=None,
            questions=questions,
        )
        codes = [f.code for f in result.findings]
        assert "KEE-VAL-001" in codes
        assert "KEE-VAL-002" in codes
        assert "KEE-VAL-004" in codes
        assert len(result.findings) == 3
