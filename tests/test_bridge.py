"""Tests for src/keel/bridge/gsd.py — first coverage for this module."""
from __future__ import annotations

from pathlib import Path

import pytest

from keel.bridge.gsd import read_gsd_state, read_gsd_roadmap, sync_goal_from_gsd


class TestReadGsdState:
    def test_absent_planning_dir_is_silent(self, tmp_path, capsys):
        result = read_gsd_state(tmp_path)
        assert result == {}
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_warns_when_state_md_has_no_current_phase(self, tmp_path, capsys):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "STATE.md").write_text("# State\n\nNo phase info here.\n", encoding="utf-8")
        result = read_gsd_state(tmp_path)
        assert result.get("current_phase") is None
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "STATE.md" in captured.err

    def test_no_warning_when_state_md_absent(self, tmp_path, capsys):
        planning = tmp_path / ".planning"
        planning.mkdir()
        # No STATE.md file
        result = read_gsd_state(tmp_path)
        assert result == {}
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_parses_current_phase_when_present(self, tmp_path, capsys):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "STATE.md").write_text(
            "## Current State\n\nCurrent Phase: 1\nCurrent Position: plan 2\n",
            encoding="utf-8",
        )
        result = read_gsd_state(tmp_path)
        assert result["current_phase"] == "1"
        captured = capsys.readouterr()
        assert captured.err == ""   # no warning when parse succeeds


class TestReadGsdRoadmap:
    def test_warns_when_roadmap_has_no_phases(self, tmp_path, capsys):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "ROADMAP.md").write_text("# Roadmap\n\nNo phases here.\n", encoding="utf-8")
        result = read_gsd_roadmap(tmp_path)
        assert result == {"phases": {}}
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "ROADMAP.md" in captured.err

    def test_no_warning_when_phases_parsed(self, tmp_path, capsys):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "ROADMAP.md").write_text(
            "## Phase 1: Fix stuff\n\n## Phase 2: Ship it\n",
            encoding="utf-8",
        )
        result = read_gsd_roadmap(tmp_path)
        assert "1" in result["phases"]
        captured = capsys.readouterr()
        assert captured.err == ""


    def test_absent_planning_dir_returns_empty_dict(self, tmp_path, capsys):
        """read_gsd_roadmap returns {} (not {"phases": {}}) when .planning absent."""
        result = read_gsd_roadmap(tmp_path)
        assert result == {}
        captured = capsys.readouterr()
        assert captured.err == ""


class TestSyncGoalFromGsd:
    def test_warns_when_phase_not_in_roadmap(self, tmp_path, capsys):
        planning = tmp_path / ".planning"
        planning.mkdir()
        (planning / "STATE.md").write_text("Current Phase: 99\n", encoding="utf-8")
        (planning / "ROADMAP.md").write_text("## Phase 1: Something\n", encoding="utf-8")
        result = sync_goal_from_gsd(tmp_path)
        assert result is None
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
