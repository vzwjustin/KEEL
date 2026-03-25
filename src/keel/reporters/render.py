from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel


def render_result(console: Console, title: str, lines: list[str], json_output: bool, payload: dict) -> None:
    if json_output:
        console.print_json(json.dumps(payload))
        return
    console.print(Panel("\n".join(lines), title=title, expand=False))


def render_artifact(console: Console, artifact, json_output: bool, summary_lines: list[str]) -> None:
    payload = artifact.model_dump(mode="json", exclude_none=True)
    render_result(console, artifact.artifact_type.title(), summary_lines, json_output, payload)
