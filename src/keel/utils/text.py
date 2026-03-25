from __future__ import annotations

import re


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "artifact"


def compact_lines(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line)
