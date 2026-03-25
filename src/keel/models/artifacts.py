from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    DETERMINISTIC = "deterministic"
    INFERRED_HIGH = "inferred-high-confidence"
    INFERRED_MEDIUM = "inferred-medium-confidence"
    HEURISTIC_LOW = "heuristic-low-confidence"
    UNRESOLVED = "unresolved"


class PriorityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SeverityLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class GoalMode(str, Enum):
    UNDERSTAND = "understand"
    DEBUG = "debug"
    FIX = "fix"
    WIRE_UP_INCOMPLETE = "wire-up-incomplete-code"
    EXTEND = "extend"
    REFACTOR = "refactor-without-behavior-change"
    HARDEN = "harden"
    ADD_FEATURE = "add-feature"
    SHIP_MVP = "ship-mvp"
    CLEAN_UP_DRIFT = "clean-up-drift"
    VERIFY_CLAIMS = "verify-implementation-claims"


class ArtifactBase(BaseModel):
    artifact_id: str
    artifact_type: str
    created_at: datetime
    repo_root: str


class ScanItem(BaseModel):
    name: str
    detail: str
    confidence: ConfidenceLevel
    evidence: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)


class ScanFinding(BaseModel):
    finding_id: str
    category: str
    title: str
    detail: str
    confidence: ConfidenceLevel
    severity: SeverityLevel
    evidence: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)


class ScanStats(BaseModel):
    file_count: int = 0
    text_file_count: int = 0
    total_bytes: int = 0


class ScanArtifact(ArtifactBase):
    artifact_type: str = "scan"
    stats: ScanStats
    languages: list[ScanItem] = Field(default_factory=list)
    build_systems: list[ScanItem] = Field(default_factory=list)
    runtime_surfaces: list[ScanItem] = Field(default_factory=list)
    entrypoints: list[ScanItem] = Field(default_factory=list)
    modules: list[ScanItem] = Field(default_factory=list)
    tests: list[ScanItem] = Field(default_factory=list)
    configs: list[ScanItem] = Field(default_factory=list)
    contracts: list[ScanItem] = Field(default_factory=list)
    findings: list[ScanFinding] = Field(default_factory=list)


class BaselineConclusion(BaseModel):
    conclusion_id: str
    category: str
    title: str
    detail: str
    confidence: ConfidenceLevel
    evidence: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)


class BaselineArtifact(ArtifactBase):
    artifact_type: str = "baseline"
    source_scan_id: str
    exists_today: list[BaselineConclusion] = Field(default_factory=list)
    authoritative: list[BaselineConclusion] = Field(default_factory=list)
    partial: list[BaselineConclusion] = Field(default_factory=list)
    stale: list[BaselineConclusion] = Field(default_factory=list)
    broken_or_ambiguous: list[BaselineConclusion] = Field(default_factory=list)
    unknowns: list[BaselineConclusion] = Field(default_factory=list)


class GoalArtifact(ArtifactBase):
    artifact_type: str = "goal"
    mode: GoalMode
    goal_statement: str
    scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class ResearchFinding(BaseModel):
    finding_id: str
    source: str
    source_type: str
    record_kind: str = "external-guidance"
    source_trust: str
    trust_rank: int
    title: str
    summary: str
    status: str
    citation: str
    confidence: ConfidenceLevel


class ResearchArtifact(ArtifactBase):
    artifact_type: str = "research"
    enabled: bool
    query: Optional[str] = None
    findings: list[ResearchFinding] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    status: str = "disabled"


class QuestionItem(BaseModel):
    question_id: str
    question: str
    why_it_matters: str
    triggered_by: str
    unblocks: str
    priority: PriorityLevel
    confidence: ConfidenceLevel
    related_paths: list[str] = Field(default_factory=list)


class QuestionArtifact(ArtifactBase):
    artifact_type: str = "questions"
    questions: list[QuestionItem] = Field(default_factory=list)


class AlignmentMismatch(BaseModel):
    mismatch_id: str
    summary: str
    detail: str
    confidence: ConfidenceLevel
    severity: SeverityLevel
    evidence: list[str] = Field(default_factory=list)


class AlignmentArtifact(ArtifactBase):
    artifact_type: str = "alignment"
    mismatches: list[AlignmentMismatch] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_decisions: list[str] = Field(default_factory=list)
    recommended_focus_area: str
    confidence_summary: str


class PlanStep(BaseModel):
    step_id: str
    title: str
    detail: str
    status: str = "pending"
    related_paths: list[str] = Field(default_factory=list)
    assumptions_to_verify: list[str] = Field(default_factory=list)
    done_definition: str


class PlanPhase(BaseModel):
    phase_id: str
    title: str
    objective: str
    done_definition: str
    steps: list[PlanStep] = Field(default_factory=list)


class PlanArtifact(ArtifactBase):
    artifact_type: str = "plan"
    focus_area: str
    phases: list[PlanPhase] = Field(default_factory=list)
    current_next_step: str


class SessionState(BaseModel):
    active_goal_id: Optional[str] = None
    active_phase_id: Optional[str] = None
    active_step_id: Optional[str] = None
    completed_step_ids: list[str] = Field(default_factory=list)
    unresolved_question_ids: list[str] = Field(default_factory=list)
    latest_decisions: list[str] = Field(default_factory=list)
    research_artifact_ids: list[str] = Field(default_factory=list)
    active_plan_id: Optional[str] = None
    current_next_step: Optional[str] = None
    drift_warnings: list[str] = Field(default_factory=list)
    latest_scan_id: Optional[str] = None
    latest_baseline_id: Optional[str] = None
    latest_alignment_id: Optional[str] = None
    latest_trace_id: Optional[str] = None
    latest_validation_id: Optional[str] = None
    latest_drift_id: Optional[str] = None


class ValidationFinding(BaseModel):
    code: str
    message: str
    severity: SeverityLevel
    confidence: ConfidenceLevel
    suggested_action: str
    paths: list[str] = Field(default_factory=list)


class ValidationArtifact(ArtifactBase):
    artifact_type: str = "validation"
    findings: list[ValidationFinding] = Field(default_factory=list)
    status: str


class TraceRow(BaseModel):
    row_id: str
    goal_reference: str
    validation_reference: str
    plan_step_ids: list[str] = Field(default_factory=list)
    status: str


class TraceArtifact(ArtifactBase):
    artifact_type: str = "trace"
    rows: list[TraceRow] = Field(default_factory=list)


class DriftFinding(BaseModel):
    code: str
    layer: str
    summary: str
    detail: str
    severity: SeverityLevel
    confidence: ConfidenceLevel
    suggested_action: str
    evidence: list[str] = Field(default_factory=list)


class DriftCluster(BaseModel):
    cluster_id: str
    layer: str
    summary: str
    detail: str
    severity: SeverityLevel
    confidence: ConfidenceLevel
    event_count: int
    related_codes: list[str] = Field(default_factory=list)
    touched_areas: list[str] = Field(default_factory=list)
    first_seen_at: str
    last_seen_at: str
    recommended_action: str
    timeline: list[str] = Field(default_factory=list)


class DriftArtifact(ArtifactBase):
    artifact_type: str = "drift"
    mode: str
    findings: list[DriftFinding] = Field(default_factory=list)
    clusters: list[DriftCluster] = Field(default_factory=list)
    status: str


class DeltaArtifact(ArtifactBase):
    artifact_type: str = "delta"
    summary: str
    impacted_paths: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    validation_mapping: list[str] = Field(default_factory=list)


class RecoveryIssue(BaseModel):
    issue_id: str
    kind: str
    summary: str
    detail: str
    severity: SeverityLevel
    confidence: ConfidenceLevel
    evidence: list[str] = Field(default_factory=list)


class RecoveryMode(BaseModel):
    mode_id: str
    label: str
    summary: str
    confidence: ConfidenceLevel
    matched_codes: list[str] = Field(default_factory=list)


class RecoveryStep(BaseModel):
    step_id: str
    title: str
    detail: str
    paths: list[str] = Field(default_factory=list)


class RecoveryArtifact(ArtifactBase):
    artifact_type: str = "recovery"
    divergence_at: str
    divergence_reason: str
    intent_replay: dict[str, str] = Field(default_factory=dict)
    issues: list[RecoveryIssue] = Field(default_factory=list)
    recovery_modes: list[RecoveryMode] = Field(default_factory=list)
    recommended_mode: str
    recovery_confidence: ConfidenceLevel
    steps: list[RecoveryStep] = Field(default_factory=list)
    brief_path: str
