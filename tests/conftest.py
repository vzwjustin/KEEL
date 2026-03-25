from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture()
def fixture_repo(tmp_path: Path):
    def _copy(name: str) -> Path:
        source = Path(__file__).parent / "fixtures" / name
        target = tmp_path / name
        shutil.copytree(source, target)
        return target

    return _copy
