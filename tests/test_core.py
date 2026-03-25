"""Tests for the core I/O layer: artifacts, paths, and bootstrap."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from keel.core.artifacts import (
    artifact_file,
    dump_json,
    latest_yaml_file,
    load_latest_model,
    load_model,
    load_model_by_artifact_id,
    load_yaml,
    save_artifact,
    save_model,
    save_yaml,
)
from keel.core.bootstrap import DEFAULT_BRIEF, ensure_file, ensure_project
from keel.core.paths import KeelPaths, now_iso, now_stamp, resolve_paths


# ---------------------------------------------------------------------------
# Minimal Pydantic model used across artifact tests
# ---------------------------------------------------------------------------

class _Simple(BaseModel):
    artifact_id: Optional[str] = None
    name: str
    value: int


# ===========================================================================
# artifacts.py
# ===========================================================================

class TestSaveLoadYaml:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "data.yaml"
        payload = {"key": "value", "nested": {"a": 1}}
        save_yaml(path, payload)
        assert load_yaml(path) == payload

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "file.yaml"
        save_yaml(path, {"x": 1})
        assert path.exists()

    def test_load_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        result = load_yaml(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_load_empty_file_returns_empty_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        assert load_yaml(path) == {}

    def test_key_order_preserved(self, tmp_path: Path) -> None:
        """save_yaml uses sort_keys=False; insertion order should survive."""
        path = tmp_path / "order.yaml"
        payload = {"z": 1, "a": 2, "m": 3}
        save_yaml(path, payload)
        loaded = load_yaml(path)
        assert list(loaded.keys()) == ["z", "a", "m"]


class TestSaveLoadModel:
    def test_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "model.yaml"
        model = _Simple(name="hello", value=42)
        save_model(path, model)
        restored = load_model(path, _Simple)
        assert restored == model

    def test_none_fields_excluded(self, tmp_path: Path) -> None:
        path = tmp_path / "model.yaml"
        model = _Simple(artifact_id=None, name="hi", value=1)
        save_model(path, model)
        raw = load_yaml(path)
        assert "artifact_id" not in raw

    def test_load_model_missing_optional_uses_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "partial.yaml"
        # Write only the required fields so optional ones keep their defaults
        save_yaml(path, {"name": "sparse", "value": 7})
        restored = load_model(path, _Simple)
        assert restored.name == "sparse"
        assert restored.value == 7
        assert restored.artifact_id is None


class TestArtifactFile:
    def test_uses_provided_artifact_id(self, tmp_path: Path) -> None:
        path = artifact_file(tmp_path, "scan", artifact_id="scan-20240101-120000")
        assert path == tmp_path / "scan-20240101-120000.yaml"

    def test_generates_name_from_prefix_and_stamp(self, tmp_path: Path) -> None:
        fixed_stamp = "20240101-120000"
        with patch("keel.core.artifacts.now_stamp", return_value=fixed_stamp):
            path = artifact_file(tmp_path, "scan")
        assert path == tmp_path / "scan-20240101-120000.yaml"

    def test_returns_yaml_extension(self, tmp_path: Path) -> None:
        path = artifact_file(tmp_path, "goal", artifact_id="goal-abc")
        assert path.suffix == ".yaml"


class TestSaveArtifact:
    def test_uses_model_artifact_id(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        model = _Simple(artifact_id="my-artifact-id", name="test", value=0)
        saved_path = save_artifact(paths, tmp_path, "simple", model)
        assert saved_path == tmp_path / "my-artifact-id.yaml"
        assert saved_path.exists()

    def test_uses_generated_name_when_no_artifact_id(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        model = _Simple(name="no-id", value=5)
        fixed_stamp = "20240101-000000"
        with patch("keel.core.artifacts.now_stamp", return_value=fixed_stamp):
            saved_path = save_artifact(paths, tmp_path, "simple", model)
        assert saved_path.name == "simple-20240101-000000.yaml"
        assert saved_path.exists()

    def test_file_content_is_loadable(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        model = _Simple(artifact_id="cid", name="content-check", value=99)
        saved_path = save_artifact(paths, tmp_path, "simple", model)
        restored = load_model(saved_path, _Simple)
        assert restored.name == "content-check"
        assert restored.value == 99


class TestLatestYamlFile:
    def test_returns_none_for_empty_directory(self, tmp_path: Path) -> None:
        assert latest_yaml_file(tmp_path) is None

    def test_returns_lexicographically_last_file(self, tmp_path: Path) -> None:
        (tmp_path / "b.yaml").write_text("b: 1")
        (tmp_path / "a.yaml").write_text("a: 1")
        (tmp_path / "c.yaml").write_text("c: 1")
        assert latest_yaml_file(tmp_path) == tmp_path / "c.yaml"

    def test_ignores_non_yaml_files(self, tmp_path: Path) -> None:
        (tmp_path / "notes.txt").write_text("hello")
        assert latest_yaml_file(tmp_path) is None

    def test_single_file(self, tmp_path: Path) -> None:
        p = tmp_path / "only.yaml"
        p.write_text("x: 1")
        assert latest_yaml_file(tmp_path) == p


class TestLoadLatestModel:
    def test_returns_none_for_empty_directory(self, tmp_path: Path) -> None:
        assert load_latest_model(tmp_path, _Simple) is None

    def test_loads_latest_file(self, tmp_path: Path) -> None:
        save_yaml(tmp_path / "a.yaml", {"name": "first", "value": 1})
        save_yaml(tmp_path / "b.yaml", {"name": "second", "value": 2})
        result = load_latest_model(tmp_path, _Simple)
        assert result is not None
        assert result.name == "second"


class TestLoadModelByArtifactId:
    def test_returns_model_when_file_exists(self, tmp_path: Path) -> None:
        save_yaml(tmp_path / "abc123.yaml", {"name": "found", "value": 7})
        result = load_model_by_artifact_id(tmp_path, "abc123", _Simple)
        assert result is not None
        assert result.name == "found"

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        result = load_model_by_artifact_id(tmp_path, "does-not-exist", _Simple)
        assert result is None

    def test_file_name_is_artifact_id_dot_yaml(self, tmp_path: Path) -> None:
        artifact_id = "my-special-id"
        save_yaml(tmp_path / f"{artifact_id}.yaml", {"name": "x", "value": 0})
        result = load_model_by_artifact_id(tmp_path, artifact_id, _Simple)
        assert result is not None


class TestDumpJson:
    def test_returns_valid_json_string(self) -> None:
        import json
        data = {"key": "value", "number": 42, "list": [1, 2, 3]}
        output = dump_json(data)
        parsed = json.loads(output)
        assert parsed == data

    def test_uses_indent_2(self) -> None:
        output = dump_json({"a": 1})
        assert "\n" in output  # indented output contains newlines

    def test_preserves_insertion_order(self) -> None:
        import json
        data = {"z": 1, "a": 2, "m": 3}
        output = dump_json(data)
        parsed = json.loads(output)
        assert list(parsed.keys()) == ["z", "a", "m"]

    def test_empty_dict(self) -> None:
        import json
        assert json.loads(dump_json({})) == {}


# ===========================================================================
# paths.py
# ===========================================================================

class TestNowStamp:
    def test_format_matches_pattern(self) -> None:
        stamp = now_stamp()
        assert re.fullmatch(r"\d{8}-\d{6}", stamp), f"Unexpected stamp: {stamp!r}"

    def test_deterministic_with_mock(self) -> None:
        fixed = datetime(2024, 6, 15, 9, 5, 3, tzinfo=timezone.utc)
        with patch("keel.core.paths.datetime") as mock_dt:
            mock_dt.now.return_value = fixed.astimezone()
            result = now_stamp()
        assert re.fullmatch(r"\d{8}-\d{6}", result)


class TestNowIso:
    def test_is_valid_iso_string(self) -> None:
        iso = now_iso()
        parsed = datetime.fromisoformat(iso)
        assert parsed is not None

    def test_contains_timezone_offset(self) -> None:
        iso = now_iso()
        # astimezone() always includes offset info (+HH:MM or -HH:MM suffix)
        assert "+" in iso or "-" in iso[10:]


class TestKeelPaths:
    def test_keel_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.keel_dir == tmp_path / ".keel"

    def test_session_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.session_dir == tmp_path / ".keel" / "session"

    def test_reports_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.reports_dir == tmp_path / ".keel" / "reports"

    def test_research_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.research_dir == tmp_path / ".keel" / "research"

    def test_prompts_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.prompts_dir == tmp_path / ".keel" / "prompts"

    def test_templates_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.templates_dir == tmp_path / ".keel" / "templates"

    def test_config_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.config_file == tmp_path / ".keel" / "config.yaml"

    def test_glossary_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.glossary_file == tmp_path / ".keel" / "glossary.yaml"

    def test_done_gate_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.done_gate_file == tmp_path / ".keel" / "done-gate.yaml"

    def test_current_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.current_file == tmp_path / ".keel" / "session" / "current.yaml"

    def test_current_brief_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.current_brief_file == tmp_path / ".keel" / "session" / "current-brief.md"

    def test_checkpoints_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.checkpoints_file == tmp_path / ".keel" / "session" / "checkpoints.yaml"

    def test_unresolved_questions_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.unresolved_questions_file == tmp_path / ".keel" / "session" / "unresolved-questions.yaml"

    def test_decisions_log_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.decisions_log_file == tmp_path / ".keel" / "session" / "decisions.log"

    def test_drift_memory_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.drift_memory_file == tmp_path / ".keel" / "session" / "drift-memory.yaml"

    def test_drift_dismissals_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.drift_dismissals_file == tmp_path / ".keel" / "session" / "drift-dismissals.yaml"

    def test_alerts_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.alerts_file == tmp_path / ".keel" / "session" / "alerts.yaml"

    def test_pending_notification_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.pending_notification_file == tmp_path / ".keel" / "session" / "pending-notification.yaml"

    def test_artifact_root(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.artifact_root == tmp_path / "keel"

    def test_discovery_root(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.discovery_root == tmp_path / "keel" / "discovery"

    def test_scans_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.scans_dir == tmp_path / "keel" / "discovery" / "scans"

    def test_baselines_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.baselines_dir == tmp_path / "keel" / "discovery" / "baselines"

    def test_goals_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.goals_dir == tmp_path / "keel" / "discovery" / "goals"

    def test_plans_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.plans_dir == tmp_path / "keel" / "discovery" / "plans"

    def test_specs_root(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.specs_root == tmp_path / "keel" / "specs"

    def test_requirements_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.requirements_dir == tmp_path / "keel" / "specs" / "requirements"

    def test_decisions_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.decisions_dir == tmp_path / "keel" / "specs" / "decisions"

    def test_contracts_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.contracts_dir == tmp_path / "keel" / "specs" / "contracts"

    def test_deltas_dir(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.deltas_dir == tmp_path / "keel" / "specs" / "deltas"

    def test_companion_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.companion_file == tmp_path / ".keel" / "session" / "companion.yaml"

    def test_companion_log_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.companion_log_file == tmp_path / ".keel" / "session" / "companion.log"

    def test_companion_heartbeat_file(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        assert paths.companion_heartbeat_file == tmp_path / ".keel" / "session" / "companion-heartbeat.yaml"

    def test_ensure_creates_all_directories(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        paths.ensure()
        expected_dirs = [
            paths.keel_dir,
            paths.session_dir,
            paths.reports_dir,
            paths.research_dir,
            paths.prompts_dir,
            paths.templates_dir,
            paths.scans_dir,
            paths.baselines_dir,
            paths.goals_dir,
            paths.questions_dir,
            paths.alignments_dir,
            paths.plans_dir,
            paths.checkpoints_dir,
            paths.research_artifacts_dir,
            paths.requirements_dir,
            paths.decisions_dir,
            paths.contracts_dir,
            paths.examples_dir,
            paths.validation_dir,
            paths.deltas_dir,
        ]
        for d in expected_dirs:
            assert d.is_dir(), f"Expected directory was not created: {d}"

    def test_ensure_is_idempotent(self, tmp_path: Path) -> None:
        paths = KeelPaths(tmp_path)
        paths.ensure()
        paths.ensure()  # second call must not raise


class TestResolvePaths:
    def test_returns_keel_paths(self, tmp_path: Path) -> None:
        result = resolve_paths(tmp_path)
        assert isinstance(result, KeelPaths)

    def test_resolves_string_root(self, tmp_path: Path) -> None:
        result = resolve_paths(str(tmp_path))
        assert isinstance(result, KeelPaths)
        assert result.root == tmp_path.resolve()

    def test_root_is_resolved(self, tmp_path: Path) -> None:
        result = resolve_paths(tmp_path)
        assert result.root == tmp_path.resolve()


# ===========================================================================
# bootstrap.py
# ===========================================================================

class TestEnsureFile:
    def test_creates_file_when_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "new.md"
        ensure_file(path, "hello")
        assert path.read_text(encoding="utf-8") == "hello"

    def test_does_not_overwrite_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "existing.md"
        path.write_text("original", encoding="utf-8")
        ensure_file(path, "replacement")
        assert path.read_text(encoding="utf-8") == "original"

    def test_creates_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.log"
        ensure_file(path, "")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == ""


class TestEnsureProject:
    def test_returns_three_tuple(self, tmp_path: Path) -> None:
        result = ensure_project(tmp_path)
        assert len(result) == 3

    def test_returns_keel_paths(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        assert isinstance(paths, KeelPaths)

    def test_creates_keel_dir_tree(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        assert paths.keel_dir.is_dir()
        assert paths.session_dir.is_dir()
        assert paths.scans_dir.is_dir()
        assert paths.requirements_dir.is_dir()

    def test_creates_config_file(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        assert paths.config_file.exists()

    def test_creates_current_yaml(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        assert paths.current_file.exists()

    def test_creates_checkpoints_yaml(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        content = load_yaml(paths.checkpoints_file)
        assert content == {"checkpoints": []}

    def test_creates_unresolved_questions_yaml(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        content = load_yaml(paths.unresolved_questions_file)
        assert content == {"questions": []}

    def test_creates_drift_memory_yaml(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        content = load_yaml(paths.drift_memory_file)
        assert content == {"events": []}

    def test_creates_drift_dismissals_yaml(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        content = load_yaml(paths.drift_dismissals_file)
        assert content == {"dismissals": []}

    def test_creates_alerts_yaml(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        content = load_yaml(paths.alerts_file)
        assert content == {"alerts": []}

    def test_creates_current_brief_with_default_content(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        assert paths.current_brief_file.exists()
        assert paths.current_brief_file.read_text(encoding="utf-8") == DEFAULT_BRIEF

    def test_creates_decisions_log_empty(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        assert paths.decisions_log_file.exists()
        assert paths.decisions_log_file.read_text(encoding="utf-8") == ""

    def test_creates_glossary_file(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        assert paths.glossary_file.exists()
        assert "terms" in paths.glossary_file.read_text(encoding="utf-8")

    def test_creates_done_gate_file(self, tmp_path: Path) -> None:
        paths, _, _ = ensure_project(tmp_path)
        assert paths.done_gate_file.exists()

    def test_returns_session_state(self, tmp_path: Path) -> None:
        from keel.models import SessionState
        _, _, session = ensure_project(tmp_path)
        assert isinstance(session, SessionState)

    def test_idempotent_on_second_call(self, tmp_path: Path) -> None:
        """Running ensure_project twice must not raise and must not corrupt files."""
        paths, _, _ = ensure_project(tmp_path)
        paths.current_brief_file.write_text("custom brief", encoding="utf-8")
        ensure_project(tmp_path)
        # The manually-written brief must survive the second call
        assert paths.current_brief_file.read_text(encoding="utf-8") == "custom brief"

    def test_does_not_overwrite_existing_current_yaml(self, tmp_path: Path) -> None:
        """Pre-existing session state must be preserved."""
        paths, _, _ = ensure_project(tmp_path)
        # Mutate current.yaml directly
        save_yaml(paths.current_file, {"active_goal_id": "g-001"})
        # Re-run
        _, _, session = ensure_project(tmp_path)
        assert session.active_goal_id == "g-001"
