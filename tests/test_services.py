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

class TestGenerateQuestions:
    def test_returns_question_artifact(self):
        from keel.questions.service import generate_questions
        result = generate_questions(repo_root="/tmp/repo", scan=None, baseline=None, goal=None, research=None)
        assert isinstance(result, QuestionArtifact)

    def test_no_criteria_triggers_question(self):
        from keel.questions.service import generate_questions
        goal = _goal(success_criteria=[])
        result = generate_questions(repo_root="/tmp/repo", scan=None, baseline=None, goal=goal, research=None)
        assert any("success criteria" in q.question.lower() for q in result.questions)

    def test_with_criteria_no_criteria_question(self):
        from keel.questions.service import generate_questions
        goal = _goal(success_criteria=["Tests pass"])
        result = generate_questions(repo_root="/tmp/repo", scan=None, baseline=None, goal=goal, research=None)
        assert not any("success criteria" in q.question.lower() for q in result.questions)

    def test_baseline_unknowns_generate_questions(self):
        from keel.questions.service import generate_questions
        baseline = _baseline()
        result = generate_questions(repo_root="/tmp/repo", scan=None, baseline=baseline, goal=None, research=None)
        assert any("unknown" in q.question.lower() for q in result.questions)

    def test_no_tests_with_behavior_mode_triggers_question(self):
        from keel.questions.service import generate_questions
        scan = _scan(tests=[])
        goal = _goal(mode=GoalMode.FIX)
        result = generate_questions(repo_root="/tmp/repo", scan=scan, baseline=None, goal=goal, research=None)
        assert any("validation" in q.question.lower() for q in result.questions)

    def test_no_tests_with_understand_mode_no_question(self):
        from keel.questions.service import generate_questions
        scan = _scan(tests=[])
        goal = _goal(mode=GoalMode.UNDERSTAND)
        result = generate_questions(repo_root="/tmp/repo", scan=scan, baseline=None, goal=goal, research=None)
        assert not any("validation signal" in q.question.lower() for q in result.questions)

    def test_duplicate_config_generates_question(self):
        from keel.questions.service import generate_questions
        finding = ScanFinding(
            finding_id="FND-001",
            title="multiple pyproject.toml files detected",
            detail="found 2", category="duplicate-config",
            severity=SeverityLevel.WARNING, confidence=ConfidenceLevel.INFERRED_HIGH,
            evidence=[], paths=["pyproject.toml", "sub/pyproject.toml"],
        )
        scan = _scan(findings=[finding])
        result = generate_questions(repo_root="/tmp/repo", scan=scan, baseline=None, goal=None, research=None)
        assert any("authoritative" in q.question.lower() for q in result.questions)

    def test_offline_research_triggers_question(self):
        from keel.questions.service import generate_questions
        research = ResearchArtifact(
            artifact_id="research-test", created_at=NOW, repo_root="/tmp/repo",
            enabled=True, status="offline", findings=[], unresolved=["no connectivity"],
        )
        result = generate_questions(repo_root="/tmp/repo", scan=None, baseline=None, goal=None, research=research)
        assert any("external guidance" in q.question.lower() for q in result.questions)

    def test_question_ids_sequential(self):
        from keel.questions.service import generate_questions
        goal = _goal(success_criteria=[])
        baseline = _baseline()
        result = generate_questions(repo_root="/tmp/repo", scan=None, baseline=baseline, goal=goal, research=None)
        ids = [q.question_id for q in result.questions]
        for i, qid in enumerate(ids, start=1):
            assert qid == f"QST-{i:03d}"


# ===================================================================
# Align tests
# ===================================================================

class TestAlignContext:
    def test_returns_alignment_artifact(self):
        from keel.align.service import align_context
        result = align_context(repo_root="/tmp/repo", scan=None, baseline=None, goal=None, research=None, questions=None)
        assert result.artifact_id.startswith("alignment-")

    def test_no_criteria_triggers_aln001(self):
        from keel.align.service import align_context
        goal = _goal(success_criteria=[])
        result = align_context(repo_root="/tmp/repo", scan=None, baseline=None, goal=goal, research=None, questions=None)
        codes = [m.mismatch_id for m in result.mismatches]
        assert "ALN-001" in codes

    def test_with_criteria_no_aln001(self):
        from keel.align.service import align_context
        goal = _goal(success_criteria=["Tests pass"])
        result = align_context(repo_root="/tmp/repo", scan=None, baseline=None, goal=goal, research=None, questions=None)
        codes = [m.mismatch_id for m in result.mismatches]
        assert "ALN-001" not in codes

    def test_no_entrypoints_with_impl_mode_triggers_aln002(self):
        from keel.align.service import align_context
        scan = _scan(entrypoints=[])
        goal = _goal(mode=GoalMode.FIX)
        result = align_context(repo_root="/tmp/repo", scan=scan, baseline=None, goal=goal, research=None, questions=None)
        codes = [m.mismatch_id for m in result.mismatches]
        assert "ALN-002" in codes

    def test_multiple_build_systems_triggers_aln003(self):
        from keel.align.service import align_context
        scan = _scan(build_systems=[
            ScanItem(name="pip", detail="pip", paths=[], confidence=ConfidenceLevel.DETERMINISTIC, evidence=[]),
            ScanItem(name="poetry", detail="poetry", paths=[], confidence=ConfidenceLevel.DETERMINISTIC, evidence=[]),
        ])
        result = align_context(repo_root="/tmp/repo", scan=scan, baseline=None, goal=None, research=None, questions=None)
        codes = [m.mismatch_id for m in result.mismatches]
        assert "ALN-003" in codes

    def test_no_tests_behavior_mode_triggers_aln004(self):
        from keel.align.service import align_context
        scan = _scan(tests=[])
        goal = _goal(mode=GoalMode.ADD_FEATURE)
        result = align_context(repo_root="/tmp/repo", scan=scan, baseline=None, goal=goal, research=None, questions=None)
        codes = [m.mismatch_id for m in result.mismatches]
        assert "ALN-004" in codes

    def test_no_tests_understand_mode_no_aln004(self):
        from keel.align.service import align_context
        scan = _scan(tests=[])
        goal = _goal(mode=GoalMode.UNDERSTAND)
        result = align_context(repo_root="/tmp/repo", scan=scan, baseline=None, goal=goal, research=None, questions=None)
        codes = [m.mismatch_id for m in result.mismatches]
        assert "ALN-004" not in codes

    def test_unresolved_decisions_set_focus(self):
        from keel.align.service import align_context
        baseline = _baseline()
        result = align_context(repo_root="/tmp/repo", scan=None, baseline=baseline, goal=None, research=None, questions=None)
        assert "unknowns" in result.recommended_focus_area.lower() or "unresolved" in result.recommended_focus_area.lower()

    def test_clean_alignment_high_confidence(self):
        from keel.align.service import align_context
        goal = _goal(success_criteria=["done"])
        result = align_context(repo_root="/tmp/repo", scan=_scan(), baseline=_baseline(unknowns=[]), goal=goal, research=None, questions=None)
        # No mismatches, no unresolved decisions from baseline
        # but questions=None means no extra unresolved_decisions added
        if not result.mismatches and not result.unresolved_decisions:
            assert "high" in result.confidence_summary.lower()

    def test_assumptions_include_goal_assumptions(self):
        from keel.align.service import align_context
        goal = _goal(assumptions=["we have Python 3.9+"])
        result = align_context(repo_root="/tmp/repo", scan=None, baseline=None, goal=goal, research=None, questions=None)
        assert "we have Python 3.9+" in result.assumptions


# ===================================================================
# Baseline tests
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

class TestBuildGuidance:
    def test_no_goal_returns_bootstrap(self):
        from keel.guide.service import build_guidance
        from keel.core.paths import KeelPaths
        paths = KeelPaths("/tmp/repo")
        result = build_guidance(paths, _session(), goal=None)
        assert "keel start" in result["current_step"].lower()
        assert "keel start" in result["suggested_commands"]

    def test_goal_no_plan_suggests_plan(self):
        from keel.guide.service import build_guidance
        from keel.core.paths import KeelPaths
        paths = KeelPaths("/tmp/repo")
        result = build_guidance(paths, _session(), goal=_goal(), plan=None)
        assert "no plan" in result["current_step"].lower()
        assert "keel plan" in result["suggested_commands"]

    def test_full_guidance_includes_phase_title(self):
        from keel.guide.service import build_guidance
        from keel.core.paths import KeelPaths
        paths = KeelPaths("/tmp/repo")
        result = build_guidance(paths, _session(), goal=_goal(), plan=_plan())
        assert "Lock Reality" in result["current_step"]

    def test_what_to_do_includes_step_detail(self):
        from keel.guide.service import build_guidance
        from keel.core.paths import KeelPaths
        paths = KeelPaths("/tmp/repo")
        result = build_guidance(paths, _session(), goal=_goal(), plan=_plan())
        assert any("verify" in item.lower() for item in result["what_to_do"])

    def test_mode_nudge_included(self):
        from keel.guide.service import build_guidance
        from keel.core.paths import KeelPaths
        paths = KeelPaths("/tmp/repo")
        result = build_guidance(paths, _session(), goal=_goal(mode=GoalMode.UNDERSTAND), plan=_plan())
        assert any("reading" in item.lower() for item in result["what_to_do"])

    def test_drift_warnings_in_output(self):
        from keel.guide.service import build_guidance
        from keel.core.paths import KeelPaths
        paths = KeelPaths("/tmp/repo")
        drift = DriftArtifact(
            artifact_id="drift-test", created_at=NOW, repo_root="/tmp/repo",
            mode="auto",
            findings=[DriftFinding(code="KEE-DRF-001", layer="repo", summary="Repo changed", detail="changed", severity=SeverityLevel.WARNING, confidence=ConfidenceLevel.INFERRED_HIGH, suggested_action="rescan", evidence=[])],
            clusters=[], status="warning",
        )
        result = build_guidance(paths, _session(), goal=_goal(), plan=_plan(), drift=drift)
        assert len(result["warnings"]) > 0
        assert any("drift" in w.lower() for w in result["warnings"])

    def test_suggested_commands_for_reconcile_phase(self):
        from keel.guide.service import build_guidance
        from keel.core.paths import KeelPaths
        paths = KeelPaths("/tmp/repo")
        plan = PlanArtifact(
            artifact_id="plan-test", created_at=NOW, repo_root="/tmp/repo",
            focus_area="test",
            phases=[PlanPhase(
                phase_id="PHASE-4", title="Reconcile", objective="close loop",
                done_definition="done",
                steps=[PlanStep(step_id="PH4-STEP1", title="Run gates", detail="check", status="pending", related_paths=[], assumptions_to_verify=[], done_definition="done")],
            )],
            current_next_step="Run gates",
        )
        session = _session(active_phase_id="PHASE-4", active_step_id="PH4-STEP1")
        result = build_guidance(paths, session, goal=_goal(), plan=plan)
        assert "keel check" in result["suggested_commands"]

    def test_context_includes_scan_data(self):
        from keel.guide.service import build_guidance
        from keel.core.paths import KeelPaths
        paths = KeelPaths("/tmp/repo")
        result = build_guidance(paths, _session(), goal=_goal(), plan=_plan(), scan=_scan())
        assert "Python" in result["context"]["languages"]

    def test_unresolved_questions_in_what_to_avoid(self):
        from keel.guide.service import build_guidance
        from keel.core.paths import KeelPaths
        paths = KeelPaths("/tmp/repo")
        goal = _goal(unresolved_questions=["What about X?"])
        result = build_guidance(paths, _session(), goal=goal, plan=_plan())
        assert any("unresolved" in item.lower() for item in result["what_to_avoid"])
