"""Tests for goal, questions, align, baseline, trace, and guide services."""
from __future__ import annotations

from datetime import datetime

import pytest

from keel.models import (
    AlignmentMismatch,
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
    ScanFinding,
    ScanItem,
    ScanStats,
    SessionState,
    SeverityLevel,
    TraceArtifact,
    ValidationArtifact,
    ValidationFinding,
    BaselineArtifact,
)

NOW = datetime.now().astimezone()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scan(**overrides) -> ScanArtifact:
    defaults = dict(
        artifact_id="scan-test",
        created_at=NOW,
        repo_root="/tmp/repo",
        languages=[ScanItem(name="Python", detail="found .py files", paths=["src/"], confidence=ConfidenceLevel.DETERMINISTIC, evidence=["*.py"])],
        build_systems=[ScanItem(name="Python packaging", detail="pyproject.toml", paths=["pyproject.toml"], confidence=ConfidenceLevel.DETERMINISTIC, evidence=["pyproject.toml"])],
        entrypoints=[ScanItem(name="main.py", detail="entry", paths=["src/main.py"], confidence=ConfidenceLevel.INFERRED_HIGH, evidence=["main"])],
        modules=[ScanItem(name="core", detail="core module", paths=["src/core/"], confidence=ConfidenceLevel.INFERRED_HIGH, evidence=[])],
        runtime_surfaces=[],
        configs=[ScanItem(name="pyproject.toml", detail="config", paths=["pyproject.toml"], confidence=ConfidenceLevel.DETERMINISTIC, evidence=["pyproject.toml"])],
        contracts=[],
        tests=[ScanItem(name="tests", detail="test dir", paths=["tests/"], confidence=ConfidenceLevel.DETERMINISTIC, evidence=["tests/"])],
        findings=[],
        stats=ScanStats(files_scanned=10, dirs_scanned=3, elapsed_seconds=0.1),
    )
    defaults.update(overrides)
    return ScanArtifact(**defaults)


def _goal(mode=GoalMode.UNDERSTAND, success_criteria=None, **overrides) -> GoalArtifact:
    defaults = dict(
        artifact_id="goal-test",
        created_at=NOW,
        repo_root="/tmp/repo",
        mode=mode,
        goal_statement="Test goal",
        scope=["src/"],
        out_of_scope=[],
        constraints=[],
        success_criteria=success_criteria or [],
        risks=[],
        assumptions=["assume X"],
        unresolved_questions=[],
    )
    defaults.update(overrides)
    return GoalArtifact(**defaults)


def _plan(**overrides) -> PlanArtifact:
    defaults = dict(
        artifact_id="plan-test",
        created_at=NOW,
        repo_root="/tmp/repo",
        focus_area="test focus",
        phases=[
            PlanPhase(
                phase_id="PHASE-1",
                title="Lock Reality",
                objective="understand",
                done_definition="done",
                steps=[
                    PlanStep(step_id="PH1-STEP1", title="Confirm source of truth", detail="verify", status="pending", related_paths=["src/"], assumptions_to_verify=["check X"], done_definition="done"),
                ],
            ),
            PlanPhase(
                phase_id="PHASE-2",
                title="Shape the Change",
                objective="plan",
                done_definition="done",
                steps=[
                    PlanStep(step_id="PH2-STEP1", title="Define change", detail="scope it", status="pending", related_paths=[], assumptions_to_verify=[], done_definition="done"),
                ],
            ),
        ],
        current_next_step="Confirm source of truth",
    )
    defaults.update(overrides)
    return PlanArtifact(**defaults)


def _session(**overrides) -> SessionState:
    defaults = dict(
        active_goal_id="goal-test",
        active_plan_id="plan-test",
        active_phase_id="PHASE-1",
        active_step_id="PH1-STEP1",
    )
    defaults.update(overrides)
    return SessionState(**defaults)


def _baseline(**overrides) -> BaselineArtifact:
    defaults = dict(
        artifact_id="baseline-test",
        created_at=NOW,
        repo_root="/tmp/repo",
        source_scan_id="scan-test",
        exists_today=[],
        authoritative=[],
        partial=[],
        stale=[],
        broken_or_ambiguous=[],
        unknowns=[BaselineConclusion(conclusion_id="BAS-UNK-001", category="unknown", title="Unknown thing", detail="unclear", confidence=ConfidenceLevel.UNRESOLVED, evidence=[], paths=[])],
    )
    defaults.update(overrides)
    return BaselineArtifact(**defaults)


# ===================================================================
# Goal tests
# ===================================================================

class TestBuildGoal:
    def test_returns_goal_artifact(self):
        from keel.goal.service import build_goal
        result = build_goal(
            repo_root="/tmp/repo", mode=GoalMode.UNDERSTAND,
            goal_statement=None, scope=None, out_of_scope=None,
            constraints=None, success_criteria=None, risks=None,
            assumptions=None, unresolved_questions=None,
        )
        assert isinstance(result, GoalArtifact)
        assert result.mode == GoalMode.UNDERSTAND

    def test_default_statement_per_mode(self):
        from keel.goal.service import build_goal
        for mode in GoalMode:
            result = build_goal(
                repo_root="/tmp/repo", mode=mode,
                goal_statement=None, scope=None, out_of_scope=None,
                constraints=None, success_criteria=None, risks=None,
                assumptions=None, unresolved_questions=None,
            )
            assert result.goal_statement, f"No default statement for {mode}"
            assert len(result.goal_statement) > 10

    def test_custom_statement_overrides_default(self):
        from keel.goal.service import build_goal
        result = build_goal(
            repo_root="/tmp/repo", mode=GoalMode.FIX,
            goal_statement="Fix the login bug",
            scope=["auth/"], out_of_scope=["docs/"],
            constraints=["no breaking changes"], success_criteria=["login works"],
            risks=["regression"], assumptions=["auth module exists"],
            unresolved_questions=["which auth?"],
        )
        assert result.goal_statement == "Fix the login bug"
        assert result.scope == ["auth/"]
        assert result.constraints == ["no breaking changes"]

    def test_empty_lists_default_to_empty(self):
        from keel.goal.service import build_goal
        result = build_goal(
            repo_root="/tmp/repo", mode=GoalMode.UNDERSTAND,
            goal_statement=None, scope=None, out_of_scope=None,
            constraints=None, success_criteria=None, risks=None,
            assumptions=None, unresolved_questions=None,
        )
        assert result.scope == []
        assert result.risks == []

    def test_artifact_id_contains_goal_prefix(self):
        from keel.goal.service import build_goal
        result = build_goal(
            repo_root="/tmp/repo", mode=GoalMode.SHIP_MVP,
            goal_statement=None, scope=None, out_of_scope=None,
            constraints=None, success_criteria=None, risks=None,
            assumptions=None, unresolved_questions=None,
        )
        assert result.artifact_id.startswith("goal-")


# ===================================================================
# Questions tests
# ===================================================================

# ===================================================================

# ===================================================================

class TestBuildBaseline:
    def test_returns_baseline_artifact(self):
        from keel.baseline.generator import build_baseline
        scan = _scan()
        result = build_baseline(scan)
        assert isinstance(result, BaselineArtifact)
        assert result.source_scan_id == scan.artifact_id

    def test_languages_in_exists_today(self):
        from keel.baseline.generator import build_baseline
        result = build_baseline(_scan())
        titles = [c.title for c in result.exists_today]
        assert "Languages present" in titles

    def test_entrypoints_in_exists_today(self):
        from keel.baseline.generator import build_baseline
        result = build_baseline(_scan())
        titles = [c.title for c in result.exists_today]
        assert "Likely entrypoints found" in titles

    def test_deterministic_config_in_authoritative(self):
        from keel.baseline.generator import build_baseline
        result = build_baseline(_scan())
        assert len(result.authoritative) > 0
        assert all(c.category == "authoritative" for c in result.authoritative)

    def test_no_authoritative_generates_unknown(self):
        from keel.baseline.generator import build_baseline
        scan = _scan(configs=[])
        result = build_baseline(scan)
        titles = [c.title for c in result.unknowns]
        assert any("authoritative" in t.lower() for t in titles)

    def test_partial_feature_finding_categorized(self):
        from keel.baseline.generator import build_baseline
        finding = ScanFinding(
            finding_id="FND-001",
            title="Incomplete feature", detail="half done",
            category="partial-feature", severity=SeverityLevel.WARNING,
            confidence=ConfidenceLevel.INFERRED_MEDIUM, evidence=[], paths=["src/half.py"],
        )
        scan = _scan(findings=[finding])
        result = build_baseline(scan)
        assert len(result.partial) > 0

    def test_stale_zone_finding_categorized(self):
        from keel.baseline.generator import build_baseline
        finding = ScanFinding(
            finding_id="FND-002",
            title="Stale code", detail="old",
            category="stale-zone", severity=SeverityLevel.INFO,
            confidence=ConfidenceLevel.HEURISTIC_LOW, evidence=[], paths=[],
        )
        scan = _scan(findings=[finding])
        result = build_baseline(scan)
        assert len(result.stale) > 0

    def test_conclusion_ids_have_prefix(self):
        from keel.baseline.generator import build_baseline
        result = build_baseline(_scan())
        for c in result.exists_today + result.authoritative + result.unknowns:
            assert c.conclusion_id.startswith("BAS-")

    def test_empty_scan_produces_unknown(self):
        from keel.baseline.generator import build_baseline
        scan = _scan(languages=[], build_systems=[], entrypoints=[], configs=[], runtime_surfaces=[])
        result = build_baseline(scan)
        assert len(result.unknowns) > 0


# ===================================================================
# Trace tests
# ===================================================================

class TestBuildTrace:
    def test_returns_trace_artifact(self):
        from keel.trace.service import build_trace
        result = build_trace(repo_root="/tmp/repo", goal=None, plan=None, validation=None)
        assert isinstance(result, TraceArtifact)

    def test_no_criteria_uses_default_message(self):
        from keel.trace.service import build_trace
        result = build_trace(repo_root="/tmp/repo", goal=None, plan=None, validation=None)
        assert len(result.rows) == 1
        assert "no explicit" in result.rows[0].goal_reference.lower()

    def test_criteria_create_rows(self):
        from keel.trace.service import build_trace
        goal = _goal(success_criteria=["Tests pass", "No regressions"])
        result = build_trace(repo_root="/tmp/repo", goal=goal, plan=None, validation=None)
        assert len(result.rows) == 2
        assert result.rows[0].goal_reference == "Tests pass"

    def test_row_ids_sequential(self):
        from keel.trace.service import build_trace
        goal = _goal(success_criteria=["A", "B", "C"])
        result = build_trace(repo_root="/tmp/repo", goal=goal, plan=None, validation=None)
        for i, row in enumerate(result.rows, start=1):
            assert row.row_id == f"TRC-{i:03d}"

    def test_linked_status_when_plan_and_validation(self):
        from keel.trace.service import build_trace
        goal = _goal(success_criteria=["OK"])
        plan = _plan()
        validation = ValidationArtifact(
            artifact_id="val-test", created_at=NOW, repo_root="/tmp/repo",
            status="ok", findings=[],
        )
        result = build_trace(repo_root="/tmp/repo", goal=goal, plan=plan, validation=validation)
        assert result.rows[0].status == "linked"

    def test_partial_status_without_validation(self):
        from keel.trace.service import build_trace
        goal = _goal(success_criteria=["OK"])
        result = build_trace(repo_root="/tmp/repo", goal=goal, plan=_plan(), validation=None)
        assert result.rows[0].status == "partial"

    def test_plan_step_ids_in_rows(self):
        from keel.trace.service import build_trace
        goal = _goal(success_criteria=["OK"])
        plan = _plan()
        result = build_trace(repo_root="/tmp/repo", goal=goal, plan=plan, validation=None)
        assert "PH1-STEP1" in result.rows[0].plan_step_ids


# ===================================================================
# Guide tests
# ===================================================================


# ===================================================================
# Goal guard tests (REQ-101)
# ===================================================================

class TestGoalGuard:
    """Tests for the goal() CLI command guard that prevents silent goal overwrites."""

    @staticmethod
    def _load_active_goal(repo):
        """Helper: load the active goal yaml from disk given a repo path."""
        import yaml as _yaml
        session_file = repo / ".keel" / "session" / "current.yaml"
        with open(session_file) as f:
            session = _yaml.safe_load(f)
        active_id = session["active_goal_id"]
        # goals_dir = {root}/keel/discovery/goals per KeelPaths
        # (artifact_root = root / "keel", not .keel / "keel")
        goals_dir = repo / "keel" / "discovery" / "goals"
        goal_file = goals_dir / f"{active_id}.yaml"
        with open(goal_file) as f:
            return _yaml.safe_load(f)

    def test_unresolved_question_appends_without_overwriting_goal(self, fixture_repo) -> None:
        """Test A: --unresolved-question appends to existing goal, does not raise TypeError."""
        from typer.testing import CliRunner
        from keel.cli.app import app
        from tests.conftest import keel_bootstrap

        repo = fixture_repo("multi_entry_repo")
        runner = CliRunner()
        keel_bootstrap(repo, runner, goal_mode="understand",
                       goal_statement="Understand the codebase thoroughly", json=True)

        original_goal = self._load_active_goal(repo)
        original_statement = original_goal["goal_statement"]

        # Invoke --unresolved-question (previously crashed with TypeError)
        result = runner.invoke(app, [
            "--repo", str(repo), "--json",
            "goal", "--unresolved-question", "Why does X fail?"
        ])
        assert result.exit_code == 0, result.stdout

        # Goal statement must be preserved
        updated_goal = self._load_active_goal(repo)
        assert updated_goal["goal_statement"] == original_statement

    def test_partial_flag_inherits_existing_goal_statement(self, fixture_repo) -> None:
        """Test B: --goal-mode fix without --goal-statement inherits existing goal_statement."""
        from typer.testing import CliRunner
        from keel.cli.app import app
        from tests.conftest import keel_bootstrap

        repo = fixture_repo("multi_entry_repo")
        runner = CliRunner()
        keel_bootstrap(repo, runner, goal_mode="understand",
                       goal_statement="My specific goal statement", json=True)

        # Invoke --goal-mode fix without --goal-statement
        result = runner.invoke(app, [
            "--repo", str(repo), "--json",
            "goal", "--goal-mode", "fix"
        ])
        assert result.exit_code == 0, result.stdout

        updated_goal = self._load_active_goal(repo)

        # Must preserve the original goal_statement, NOT replace with FIX default
        assert updated_goal["goal_statement"] == "My specific goal statement"
        assert "Implement the next planned feature" not in updated_goal["goal_statement"]

    def test_explicit_goal_statement_always_wins(self, fixture_repo) -> None:
        """Test C: explicit --goal-statement creates new goal regardless of existing session."""
        from typer.testing import CliRunner
        from keel.cli.app import app
        from tests.conftest import keel_bootstrap

        repo = fixture_repo("multi_entry_repo")
        runner = CliRunner()
        keel_bootstrap(repo, runner, goal_mode="understand",
                       goal_statement="Old goal statement", json=True)

        # Invoke with explicit new goal statement
        result = runner.invoke(app, [
            "--repo", str(repo), "--json",
            "goal", "--goal-statement", "Brand new goal"
        ])
        assert result.exit_code == 0, result.stdout

        updated_goal = self._load_active_goal(repo)
        assert updated_goal["goal_statement"] == "Brand new goal"


# ---------------------------------------------------------------------------
# TestRelatedPaths — unit tests for _related_paths() and _git_hot_files()
# ---------------------------------------------------------------------------

class TestRelatedPaths:
    def test_goal_scope_path_ranked_first(self):
        from keel.planner.service import _related_paths
        scan = _scan(
            entrypoints=[
                ScanItem(name="main", detail="", paths=["src/main.py"], confidence=ConfidenceLevel.INFERRED_HIGH, evidence=[]),
                ScanItem(name="important", detail="", paths=["src/important.py"], confidence=ConfidenceLevel.INFERRED_HIGH, evidence=[]),
            ]
        )
        goal = _goal(scope=["src/important.py"])
        result = _related_paths(scan, goal=goal)
        assert result[0] == "src/important.py"

    def test_no_goal_backward_compatible(self):
        from keel.planner.service import _related_paths
        scan = _scan()
        result_with = _related_paths(scan, goal=None)
        result_without = _related_paths(scan)
        assert result_with == result_without

    def test_keyword_match_scores_higher(self):
        from keel.planner.service import _related_paths
        scan = _scan(
            entrypoints=[
                ScanItem(name="other", detail="", paths=["src/other.py"], confidence=ConfidenceLevel.INFERRED_HIGH, evidence=[]),
                ScanItem(name="parser", detail="", paths=["src/parser.py"], confidence=ConfidenceLevel.INFERRED_HIGH, evidence=[]),
            ]
        )
        goal = _goal(goal_statement="fix the parser module", scope=[])
        result = _related_paths(scan, goal=goal)
        assert "src/parser.py" in result
        assert result.index("src/parser.py") < result.index("src/other.py")

    def test_git_hot_files_returns_list_in_non_git_dir(self, tmp_path):
        from keel.planner.service import _git_hot_files
        result = _git_hot_files(tmp_path)
        assert isinstance(result, list)  # never raises, always returns list

