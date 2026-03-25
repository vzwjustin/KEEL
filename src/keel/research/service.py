from __future__ import annotations

import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from keel.config import KeelConfig
from keel.models import ConfidenceLevel, ResearchArtifact, ResearchFinding


def _fetch_url(url: str, timeout: int) -> Tuple[str, str]:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        raw = response.read(4000).decode("utf-8", errors="ignore")
    title_match = re.search(r"<title>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else url
    summary = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()
    return title, summary[:500]


def _trust_for_source(source: str) -> Tuple[str, int]:
    lowered = source.lower()
    if lowered.startswith("https://") and any(
        token in lowered for token in (".gov", ".edu", "docs.", "spec", "standards", "ietf", "w3.org", "python.org")
    ):
        return "official-docs", 1
    if lowered.startswith("https://") and any(token in lowered for token in ("github.com", "gitlab.com")):
        return "maintainer-docs", 2
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return "community-source", 3
    return "local-file", 1


def run_research(
    *,
    repo_root: str,
    config: KeelConfig,
    enabled: bool,
    query: Optional[str] = None,
    sources: Optional[list[str]] = None,
) -> ResearchArtifact:
    sources = sources or []
    findings: list[ResearchFinding] = []
    unresolved: list[str] = []
    status = "disabled"

    if not enabled:
        return ResearchArtifact(
            artifact_id=f"research-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
            created_at=datetime.now().astimezone(),
            repo_root=repo_root,
            enabled=False,
            query=query,
            findings=[],
            unresolved=["Research is disabled in the active config or command invocation."],
            status="disabled",
        )

    status = "no-input"
    if query and not sources:
        unresolved.append(
            "A research query was provided, but no local provider or explicit source URLs were configured."
        )

    for index, source in enumerate(sources, start=1):
        finding_id = f"RSR-{index:03d}"
        if source.startswith("http://") or source.startswith("https://"):
            try:
                title, summary = _fetch_url(source, config.research_timeout_seconds)
                findings.append(
                    ResearchFinding(
                        finding_id=finding_id,
                        source=source,
                        source_type="url",
                        source_trust=_trust_for_source(source)[0],
                        trust_rank=_trust_for_source(source)[1],
                        title=title,
                        summary=summary,
                        status="fetched",
                        citation=source,
                        confidence=ConfidenceLevel.INFERRED_MEDIUM,
                    )
                )
                status = "ok"
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                unresolved.append(f"Could not fetch {source}: {exc}")
                findings.append(
                    ResearchFinding(
                        finding_id=finding_id,
                        source=source,
                        source_type="url",
                        source_trust=_trust_for_source(source)[0],
                        trust_rank=_trust_for_source(source)[1],
                        title=source,
                        summary="Source fetch failed. KEEL stayed honest and continued in reduced-confidence mode.",
                        status="offline",
                        citation=source,
                        confidence=ConfidenceLevel.UNRESOLVED,
                    )
                )
                status = "offline"
        else:
            path = Path(source)
            if path.exists():
                excerpt = path.read_text(encoding="utf-8", errors="ignore")[:500]
                findings.append(
                    ResearchFinding(
                        finding_id=finding_id,
                        source=str(path.resolve()),
                        source_type="file",
                        source_trust=_trust_for_source(source)[0],
                        trust_rank=_trust_for_source(source)[1],
                        title=path.name,
                        summary=excerpt.strip(),
                        status="loaded",
                        citation=str(path.resolve()),
                        confidence=ConfidenceLevel.DETERMINISTIC,
                    )
                )
                status = "ok"
            else:
                unresolved.append(f"Research source not found: {source}")

    return ResearchArtifact(
        artifact_id=f"research-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=repo_root,
        enabled=enabled,
        query=query,
        findings=findings,
        unresolved=unresolved,
        status=status,
    )
