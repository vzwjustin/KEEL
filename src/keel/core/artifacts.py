from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TypeVar

import yaml
from pydantic import BaseModel

from keel.core.paths import KeelPaths, now_stamp

ModelT = TypeVar("ModelT", bound=BaseModel)


def save_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def save_model(path: Path, model: BaseModel) -> None:
    save_yaml(path, model.model_dump(mode="json", exclude_none=True))


def load_model(path: Path, model_type: type[ModelT]) -> ModelT:
    return model_type.model_validate(load_yaml(path))


def artifact_file(directory: Path, prefix: str, artifact_id: Optional[str] = None) -> Path:
    name = artifact_id or f"{prefix}-{now_stamp()}"
    return directory / f"{name}.yaml"


def save_artifact(paths: KeelPaths, directory: Path, prefix: str, model: BaseModel) -> Path:
    path = artifact_file(directory, prefix, getattr(model, "artifact_id", None))
    save_model(path, model)
    return path


def latest_yaml_file(directory: Path) -> Optional[Path]:
    files = sorted(directory.glob("*.yaml"))
    return files[-1] if files else None


def load_latest_model(directory: Path, model_type: type[ModelT]) -> Optional[ModelT]:
    latest = latest_yaml_file(directory)
    if latest is None:
        return None
    return load_model(latest, model_type)


def load_model_by_artifact_id(directory: Path, artifact_id: str, model_type: type[ModelT]) -> Optional[ModelT]:
    path = directory / f"{artifact_id}.yaml"
    if not path.exists():
        return None
    return load_model(path, model_type)


def dump_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=False)
