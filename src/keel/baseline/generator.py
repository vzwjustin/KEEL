from __future__ import annotations

from datetime import datetime

from keel.models import BaselineArtifact, BaselineConclusion, ConfidenceLevel, ScanArtifact


def _conclusion(
    category: str,
    title: str,
    detail: str,
    confidence: ConfidenceLevel,
    evidence: list[str],
    paths: list[str],
    index: int,
) -> BaselineConclusion:
    return BaselineConclusion(
        conclusion_id=f"BAS-{category[:3].upper()}-{index:03d}",
        category=category,
        title=title,
        detail=detail,
        confidence=confidence,
        evidence=evidence,
        paths=paths,
    )


def build_baseline(scan: ScanArtifact) -> BaselineArtifact:
    exists_today = []
    authoritative = []
    partial = []
    stale = []
    ambiguous = []
    unknowns = []

    index = 1
    if scan.languages:
        exists_today.append(
            _conclusion(
                "exists",
                "Languages present",
                ", ".join(item.name for item in scan.languages),
                ConfidenceLevel.DETERMINISTIC,
                [item.detail for item in scan.languages],
                [],
                index,
            )
        )
        index += 1
    if scan.runtime_surfaces:
        exists_today.append(
            _conclusion(
                "exists",
                "Runtime surfaces inferred",
                ", ".join(item.name for item in scan.runtime_surfaces),
                ConfidenceLevel.INFERRED_HIGH,
                [item.detail for item in scan.runtime_surfaces],
                [path for item in scan.runtime_surfaces for path in item.paths[:1]],
                index,
            )
        )
        index += 1
    if scan.entrypoints:
        exists_today.append(
            _conclusion(
                "exists",
                "Likely entrypoints found",
                ", ".join(item.name for item in scan.entrypoints[:4]),
                ConfidenceLevel.INFERRED_HIGH,
                [item.detail for item in scan.entrypoints[:4]],
                [path for item in scan.entrypoints[:4] for path in item.paths],
                index,
            )
        )
        index += 1

    for item in scan.configs:
        if item.confidence == ConfidenceLevel.DETERMINISTIC:
            authoritative.append(
                _conclusion(
                    "authoritative",
                    f"Potential source of truth: {item.name}",
                    item.detail,
                    item.confidence,
                    item.evidence,
                    item.paths,
                    index,
                )
            )
            index += 1

    for finding in scan.findings:
        target = None
        if finding.category == "partial-feature":
            target = partial
        elif finding.category == "stale-zone":
            target = stale
        elif finding.confidence == ConfidenceLevel.UNRESOLVED:
            target = unknowns
        elif finding.severity.value in {"warning", "error", "blocker"}:
            target = ambiguous
        if target is not None:
            target.append(
                _conclusion(
                    finding.category,
                    finding.title,
                    finding.detail,
                    finding.confidence,
                    finding.evidence,
                    finding.paths,
                    index,
                )
            )
            index += 1

    if not authoritative:
        unknowns.append(
            _conclusion(
                "unknown",
                "Authoritative config is not obvious",
                "KEEL found no high-confidence authoritative config among the scanned files.",
                ConfidenceLevel.UNRESOLVED,
                [],
                [],
                index,
            )
        )
        index += 1

    return BaselineArtifact(
        artifact_id=f"baseline-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=".",
        source_scan_id=scan.artifact_id,
        exists_today=exists_today,
        authoritative=authoritative,
        partial=partial,
        stale=stale,
        broken_or_ambiguous=ambiguous,
        unknowns=unknowns,
    )
