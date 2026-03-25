from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from keel.cli.app import app


@pytest.fixture()
def fixture_repo(tmp_path: Path):
    def _copy(name: str) -> Path:
        source = Path(__file__).parent / "fixtures" / name
        target = tmp_path / name
        shutil.copytree(source, target)
        return target

    return _copy


def keel_bootstrap(repo: Path, runner: CliRunner | None = None, **goal_kwargs) -> None:
    """Replace the removed 'keel start' by running init + scan + baseline + goal."""
    r = runner or CliRunner()
    goal_mode = goal_kwargs.pop("goal_mode", "understand")
    json_flag = goal_kwargs.pop("json", False)
    base = ["--repo", str(repo)]
    if json_flag:
        base = ["--repo", str(repo), "--json"]

    assert r.invoke(app, base + ["init"]).exit_code == 0
    assert r.invoke(app, base + ["scan"]).exit_code == 0
    assert r.invoke(app, base + ["baseline"]).exit_code == 0

    goal_cmd = base + ["goal", "--goal-mode", goal_mode]
    for key, values in goal_kwargs.items():
        flag = f"--{key.replace('_', '-')}"
        if isinstance(values, list):
            for v in values:
                goal_cmd.extend([flag, v])
        else:
            goal_cmd.extend([flag, values])
    result = r.invoke(app, goal_cmd)
    assert result.exit_code == 0, result.stdout
