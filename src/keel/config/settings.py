from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class StrictnessProfile(str, Enum):
    RELAXED = "relaxed"
    STANDARD = "standard"
    STRICT = "strict"
    PARANOID = "paranoid"


class KeelConfig(BaseModel):
    strictness: StrictnessProfile = StrictnessProfile.STANDARD
    research_enabled: bool = False
    research_timeout_seconds: int = 6
    max_scan_files: int = 4000
    ignored_directories: list[str] = Field(
        default_factory=lambda: [
            ".git",
            ".hg",
            ".svn",
            ".venv",
            "venv",
            "node_modules",
            "dist",
            "build",
            "coverage",
            ".pytest_cache",
            "__pycache__",
        ]
    )
    authoritative_config_names: list[str] = Field(
        default_factory=lambda: [
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "docker-compose.yml",
            "docker-compose.yaml",
            "Makefile",
        ]
    )
    output_format: str = "text"
    non_authoritative_path_parts: list[str] = Field(
        default_factory=lambda: [
            "fixtures",
            "testdata",
            "samples",
            "examples",
            "vendor",
            "third_party",
        ]
    )


def load_config(path: Path) -> KeelConfig:
    if not path.exists():
        return KeelConfig()
    data = yaml.safe_load(path.read_text()) or {}
    return KeelConfig.model_validate(data)


def save_config(path: Path, config: KeelConfig) -> None:
    path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
