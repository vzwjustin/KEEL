from __future__ import annotations

from pathlib import Path
from typing import Optional

from keel.core.artifacts import load_yaml, save_yaml
from keel.core.paths import KeelPaths, now_iso
from keel.models import (
    AlignmentArtifact,
    BaselineArtifact,
    GoalArtifact,
    PlanArtifact,
    QuestionArtifact,
    ResearchArtifact,
    ScanArtifact,
    SessionState,
)
from keel.models.artifacts import PlanPhase, PlanStep


class SessionService:
    def __init__(self, paths: KeelPaths):
        self.paths = paths

    def load(self) -> SessionState:
        return SessionState.model_validate(load_yaml(self.paths.current_file))

    def save(self, session: SessionState) -> SessionState:
        save_yaml(self.paths.current_file, session.model_dump(mode="json", exclude_none=True))
        return session

    def load_decisions(self, limit: int = 10) -> list[str]:
        if not self.paths.decisions_log_file.exists():
            return []
        lines = [
            line.strip()
            for line in self.paths.decisions_log_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        decisions = []
        seen = set()
        for line in lines[-limit:]:
            parts = line.split(" ", 1)
            decision = parts[1] if len(parts) == 2 else line
            if decision in seen:
                continue
            seen.add(decision)
            decisions.append(decision)
        return decisions

    def load_unresolved_questions(self) -> list[dict]:
        payload = load_yaml(self.paths.unresolved_questions_file)
        return payload.get("questions", [])

    def sync_questions(self, session: SessionState, questions: QuestionArtifact) -> SessionState:
        payload = {
            "questions": [question.model_dump(mode="json", exclude_none=True) for question in questions.questions]
        }
        save_yaml(self.paths.unresolved_questions_file, payload)
        session.unresolved_question_ids = [question.question_id for question in questions.questions]
        return self.save(session)

    def sync_report_state(
        self,
        session: SessionState,
        *,
        validation_id: Optional[str] = None,
        drift_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        drift_warnings: Optional[list[str]] = None,
    ) -> SessionState:
        if validation_id:
            session.latest_validation_id = validation_id
        if drift_id:
            session.latest_drift_id = drift_id
        if trace_id:
            session.latest_trace_id = trace_id
        if drift_warnings is not None:
            session.drift_warnings = drift_warnings
        return self.save(session)

    def update_from_start_flow(
        self,
        session: SessionState,
        *,
        scan: ScanArtifact,
        baseline: BaselineArtifact,
        goal: GoalArtifact,
        research: Optional[ResearchArtifact],
        questions: QuestionArtifact,
        alignment: AlignmentArtifact,
        plan: PlanArtifact,
    ) -> SessionState:
        session.active_goal_id = goal.artifact_id
        session.latest_scan_id = scan.artifact_id
        session.latest_baseline_id = baseline.artifact_id
        session.active_plan_id = plan.artifact_id
        session.latest_alignment_id = alignment.artifact_id
        session.active_phase_id = plan.phases[0].phase_id if plan.phases else None
        session.active_step_id = plan.phases[0].steps[0].step_id if plan.phases and plan.phases[0].steps else None
        session.current_next_step = plan.current_next_step
        session.research_artifact_ids = (
            [research.artifact_id] if research and research.status != "disabled" else []
        )
        session = self.sync_questions(session, questions)
        return self.save(session)

    def write_current_brief(
        self,
        *,
        goal: Optional[GoalArtifact],
        plan: Optional[PlanArtifact],
        baseline: Optional[BaselineArtifact],
        alignment: Optional[AlignmentArtifact],
        research: Optional[ResearchArtifact],
        unresolved_questions: list[str],
        decisions: list[str],
        blockers: Optional[list[str]] = None,
        must_not_change: Optional[list[str]] = None,
    ) -> Path:
        goal_text = goal.goal_statement if goal else "not set"
        phase = plan.phases[0].title if plan and plan.phases else "not set"
        step = plan.current_next_step if plan else "not set"
        constraints = ", ".join(goal.constraints[:3]) if goal and goal.constraints else "none recorded"
        question_text = ", ".join(unresolved_questions[:4]) if unresolved_questions else "none recorded"
        decision_text = ", ".join(decisions[:4]) if decisions else "none recorded"
        blocker_text = ", ".join((blockers or [])[:4]) if blockers else "none recorded"
        invariants = must_not_change or []
        if not invariants and goal:
            invariants = goal.out_of_scope[:2] + goal.constraints[:2]
        invariant_text = ", ".join(invariants[:4]) if invariants else "none recorded"
        research_text = (
            ", ".join(finding.title for finding in research.findings[:2])
            if research and research.findings
            else "offline or no active research"
        )
        facts = []
        if baseline and baseline.exists_today:
            facts = [item.title for item in baseline.exists_today[:3]]
        critical_facts = ", ".join(facts) if facts else "repo state not summarized yet"
        done_condition = alignment.recommended_focus_area if alignment else "finish the active plan step"
        body = "\n".join(
            [
                "# Current Brief",
                "",
                f"- Current goal: {goal_text}",
                f"- Current phase: {phase}",
                f"- Next step: {step}",
                f"- Blockers: {blocker_text}",
                f"- Must not change: {invariant_text}",
                f"- Constraints: {constraints}",
                f"- Unresolved questions: {question_text}",
                f"- Latest decisions: {decision_text}",
                f"- Research that matters now: {research_text}",
                f"- Critical repo facts: {critical_facts}",
                f"- Done condition for current work: {done_condition}",
            ]
        )
        self.paths.current_brief_file.write_text(body + "\n", encoding="utf-8")
        return self.paths.current_brief_file

    def record_decision(self, session: SessionState, summary: str) -> SessionState:
        with self.paths.decisions_log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{now_iso()} {summary}\n")
        session.latest_decisions = self.load_decisions()
        return self.save(session)

    def advance_step(self, session: SessionState, plan: PlanArtifact) -> tuple[SessionState, str]:
        if not plan or not plan.phases:
            session.current_next_step = "No plan phases available."
            return self.save(session), "No plan phases available."

        # Mark current step as completed
        if session.active_step_id and session.active_step_id not in session.completed_step_ids:
            session.completed_step_ids.append(session.active_step_id)

        # Build a flat list of (phase, step) pairs
        all_steps: list[tuple[PlanPhase, PlanStep]] = []
        for phase in plan.phases:
            for step in phase.steps:
                all_steps.append((phase, step))

        # Find the next uncompleted step
        next_phase = None
        next_step = None
        for phase, step in all_steps:
            if step.step_id not in session.completed_step_ids:
                next_phase = phase
                next_step = step
                break

        if next_step is None:
            # All steps complete
            session.active_step_id = None
            session.current_next_step = "All plan steps complete \u2014 run keel done"
            return self.save(session), "All plan steps complete \u2014 run keel done"

        session.active_step_id = next_step.step_id
        session.active_phase_id = next_phase.phase_id
        session.current_next_step = next_step.title
        return self.save(session), f"Advanced to: {next_step.title}"

    def add_checkpoint(self, note: str, session: SessionState, *, kind: str = "manual") -> None:
        payload = load_yaml(self.paths.checkpoints_file)
        checkpoints = payload.get("checkpoints", [])
        checkpoints.append(
            {
                "created_at": now_iso(),
                "kind": kind,
                "note": note,
                "active_goal_id": session.active_goal_id,
                "active_plan_id": session.active_plan_id,
                "active_step_id": session.active_step_id,
            }
        )
        save_yaml(self.paths.checkpoints_file, {"checkpoints": checkpoints})
