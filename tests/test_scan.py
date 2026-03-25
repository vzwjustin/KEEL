from __future__ import annotations

from keel.config import KeelConfig
from keel.discovery import scan_repository


def test_scan_detects_languages_and_partial_signals(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    artifact = scan_repository(repo, KeelConfig())

    language_names = {item.name for item in artifact.languages}
    finding_titles = {item.title for item in artifact.findings}

    assert "Python" in language_names
    assert any(item.name == "Python packaging" for item in artifact.build_systems)
    assert any(item.name == "main.py" for item in artifact.entrypoints)
    assert "TODO/FIXME/HACK markers present" in finding_titles
