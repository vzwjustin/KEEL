from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from keel.config import KeelConfig
from keel.models import ConfidenceLevel, ScanArtifact, ScanFinding, ScanItem, ScanStats, SeverityLevel

LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".rb": "Ruby",
    ".php": "PHP",
    ".sh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".md": "Markdown",
}

BUILD_MARKERS = {
    "pyproject.toml": "Python packaging",
    "requirements.txt": "Python requirements",
    "package.json": "Node package",
    "Cargo.toml": "Rust cargo",
    "go.mod": "Go modules",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "Makefile": "Make",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
}

CONTRACT_SUFFIXES = {".proto", ".graphql", ".gql", ".avsc", ".openapi.yaml", ".openapi.yml"}
TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".swift",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".rb",
    ".php",
    ".sh",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".md",
    ".txt",
}
NON_RUNTIME_PARTS = {"fixtures", "testdata", "samples", "examples"}
NON_AUTHORITATIVE_PARTS = NON_RUNTIME_PARTS | {"vendor", "third_party"}


def _item(name: str, detail: str, confidence: ConfidenceLevel, evidence: list[str], paths: list[str]) -> ScanItem:
    return ScanItem(name=name, detail=detail, confidence=confidence, evidence=evidence, paths=paths)


def _finding(
    finding_id: str,
    category: str,
    title: str,
    detail: str,
    confidence: ConfidenceLevel,
    severity: SeverityLevel,
    evidence: list[str],
    paths: list[str],
) -> ScanFinding:
    return ScanFinding(
        finding_id=finding_id,
        category=category,
        title=title,
        detail=detail,
        confidence=confidence,
        severity=severity,
        evidence=evidence,
        paths=paths,
    )


def _read_excerpt(path: Path, max_chars: int = 1200) -> str:
    try:
        return path.read_text(encoding="utf-8")[:max_chars]
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="ignore")[:max_chars]
    except OSError:
        return ""


def scan_repository(root: Path, config: KeelConfig) -> ScanArtifact:
    root = root.resolve()
    suffix_counts: Counter[str] = Counter()
    stats = ScanStats()
    build_markers: list[ScanItem] = []
    configs: list[ScanItem] = []
    contracts: list[ScanItem] = []
    entrypoints: list[ScanItem] = []
    runtime_surfaces: dict[str, ScanItem] = {}
    modules: list[ScanItem] = []
    tests: list[ScanItem] = []
    findings: list[ScanFinding] = []
    manifest_locations: defaultdict[str, list[str]] = defaultdict(list)
    top_level_dirs: set[str] = set()
    todo_hits: list[str] = []
    stale_hits: list[str] = []
    partial_hits: list[str] = []
    readme_mentions: list[str] = []
    files_seen = 0

    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in config.ignored_directories]
        current_path = Path(current_root)
        rel_root = current_path.relative_to(root)
        if rel_root.parts:
            top_level_dirs.add(rel_root.parts[0])
            for part in rel_root.parts:
                lowered = part.lower()
                if any(token in lowered for token in ("legacy", "deprecated", "archive", "backup", "old")):
                    stale_hits.append(str(rel_root))
        for filename in filenames:
            if files_seen >= config.max_scan_files:
                break
            path = current_path / filename
            rel_path = path.relative_to(root)
            files_seen += 1
            stats.file_count += 1
            try:
                stats.total_bytes += path.stat().st_size
            except OSError:
                pass

            suffix = "".join(path.suffixes[-2:]) if len(path.suffixes) > 1 else path.suffix
            suffix_counts[LANGUAGE_BY_SUFFIX.get(path.suffix, "other")] += 1

            if filename in BUILD_MARKERS and not (set(part.lower() for part in rel_path.parts) & set(config.non_authoritative_path_parts)):
                detail = BUILD_MARKERS[filename]
                build_markers.append(
                    _item(detail, f"Detected via {filename}", ConfidenceLevel.DETERMINISTIC, [str(rel_path)], [str(rel_path)])
                )
                manifest_locations[filename].append(str(rel_path))

            is_text = path.suffix.lower() in TEXT_SUFFIXES or filename in {"Dockerfile", "Makefile"}
            if is_text:
                stats.text_file_count += 1
                excerpt = _read_excerpt(path)
                if re.search(r"\b(TODO|FIXME|HACK)\b", excerpt):
                    todo_hits.append(str(rel_path))
                if any(token in filename.lower() for token in ("wip", "draft", "todo", "temp")):
                    partial_hits.append(str(rel_path))
                if filename.lower() == "readme.md":
                    readme_mentions.append(excerpt.lower())

            parts = {part.lower() for part in rel_path.parts}
            non_authoritative = bool(parts & set(config.non_authoritative_path_parts))

            if (
                filename in config.authoritative_config_names
                or path.suffix.lower() in {".yaml", ".yml", ".toml", ".json", ".ini"}
                and any(token in filename.lower() for token in ("config", "settings", "compose", "env"))
            ) and not non_authoritative:
                configs.append(
                    _item(
                        filename,
                        "Likely configuration artifact",
                        ConfidenceLevel.DETERMINISTIC if filename in config.authoritative_config_names else ConfidenceLevel.INFERRED_HIGH,
                        [str(rel_path)],
                        [str(rel_path)],
                    )
                )

            if suffix in CONTRACT_SUFFIXES or any(
                token in filename.lower() for token in ("openapi", "schema", "contract", "interface")
            ):
                contracts.append(
                    _item(
                        filename,
                        "Possible contract or schema file",
                        ConfidenceLevel.DETERMINISTIC if suffix in CONTRACT_SUFFIXES else ConfidenceLevel.INFERRED_MEDIUM,
                        [str(rel_path)],
                        [str(rel_path)],
                    )
                )

            lowered = filename.lower()
            if not (parts & NON_RUNTIME_PARTS):
                if lowered in {"main.py", "__main__.py", "manage.py", "app.py", "server.py", "cli.py"} or (
                    path.parent.name in {"bin", "scripts", "cmd"} and os.access(path, os.X_OK)
                ):
                    entrypoints.append(
                        _item(
                            filename,
                            "Likely entrypoint based on file name or executable location",
                            ConfidenceLevel.INFERRED_HIGH,
                            [str(rel_path)],
                            [str(rel_path)],
                        )
                    )

                if {"cli", "command", "commands"} & parts:
                    runtime_surfaces.setdefault(
                        "CLI",
                        _item(
                            "CLI",
                            "Directory structure suggests a command-line surface",
                            ConfidenceLevel.INFERRED_HIGH,
                            [str(rel_path)],
                            [str(rel_path)],
                        ),
                    )
                if {"api", "routes", "controllers"} & parts or lowered in {"server.py", "app.py", "asgi.py", "wsgi.py"}:
                    runtime_surfaces.setdefault(
                        "API/Server",
                        _item(
                            "API/Server",
                            "Directory or file naming suggests an API or server surface",
                            ConfidenceLevel.INFERRED_HIGH,
                            [str(rel_path)],
                            [str(rel_path)],
                        ),
                    )

            if path.parent.name in {"tests", "test"} or lowered.startswith("test_") or lowered.endswith("_test.py"):
                tests.append(
                    _item(
                        filename,
                        "Test file or test directory match",
                        ConfidenceLevel.DETERMINISTIC,
                        [str(rel_path)],
                        [str(rel_path)],
                    )
                )

        if files_seen >= config.max_scan_files:
            break

    code_root_candidates = []
    for candidate in ["src", "app", "lib", "pkg"]:
        candidate_path = root / candidate
        if candidate_path.exists():
            code_root_candidates.append(candidate_path)
    for candidate in code_root_candidates:
        for child in sorted(candidate.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                modules.append(
                    _item(
                        child.name,
                        f"Module boundary inferred from top-level directory under {candidate.name}",
                        ConfidenceLevel.INFERRED_HIGH,
                        [str(child.relative_to(root))],
                        [str(child.relative_to(root))],
                    )
                )

    for dirname in sorted(top_level_dirs):
        if dirname not in {"src", "tests", "docs", ".keel", "keel"} and dirname not in config.non_authoritative_path_parts:
            candidate = root / dirname
            if candidate.is_dir() and any(file.is_file() for file in candidate.iterdir()):
                modules.append(
                    _item(
                        dirname,
                        "Top-level directory may mark a subsystem boundary",
                        ConfidenceLevel.INFERRED_MEDIUM,
                        [dirname],
                        [dirname],
                    )
                )

    language_items = []
    for language, count in suffix_counts.items():
        if language == "other":
            continue
        language_items.append(
            _item(
                language,
                f"{count} matching files detected",
                ConfidenceLevel.DETERMINISTIC,
                [f"{count} files"],
                [],
            )
        )
    language_items.sort(key=lambda item: item.name)

    if not entrypoints:
        findings.append(
            _finding(
                "SCN-001",
                "entrypoint",
                "No clear runtime entrypoint found",
                "KEEL could not identify a likely repo entrypoint from common filenames or executable paths.",
                ConfidenceLevel.UNRESOLVED,
                SeverityLevel.WARNING,
                [],
                [],
            )
        )
    if len(build_markers) > 1:
        findings.append(
            _finding(
                "SCN-002",
                "build-system",
                "Multiple build systems detected",
                "The repository contains more than one build or packaging marker and may need a declared source of truth.",
                ConfidenceLevel.INFERRED_MEDIUM,
                SeverityLevel.WARNING,
                [item.name for item in build_markers],
                [path for item in build_markers for path in item.paths],
            )
        )
    if not tests:
        findings.append(
            _finding(
                "SCN-003",
                "tests",
                "No tests detected",
                "KEEL did not find test files or test directories in the scanned portion of the repository.",
                ConfidenceLevel.DETERMINISTIC,
                SeverityLevel.WARNING,
                [],
                [],
            )
        )
    if todo_hits:
        findings.append(
            _finding(
                "SCN-004",
                "partial-feature",
                "TODO/FIXME/HACK markers present",
                f"Found {len(todo_hits)} files with implementation debt markers, which may indicate partial or unstable flows.",
                ConfidenceLevel.DETERMINISTIC,
                SeverityLevel.INFO,
                todo_hits[:8],
                todo_hits[:8],
            )
        )
    for manifest, locations in manifest_locations.items():
        if len(locations) > 1:
            findings.append(
                _finding(
                    f"SCN-DUP-{manifest}",
                    "duplicate-config",
                    f"Multiple {manifest} files detected",
                    "Duplicate manifest names can signal split ownership or conflicting configuration.",
                    ConfidenceLevel.INFERRED_HIGH,
                    SeverityLevel.WARNING,
                    locations[:8],
                    locations[:8],
                )
            )
    if stale_hits:
        findings.append(
            _finding(
                "SCN-005",
                "stale-zone",
                "Stale-looking zones detected",
                "Directory names suggest archived, deprecated, backup, or old code paths that may need verification.",
                ConfidenceLevel.HEURISTIC_LOW,
                SeverityLevel.INFO,
                stale_hits[:8],
                stale_hits[:8],
            )
        )
    if partial_hits:
        findings.append(
            _finding(
                "SCN-006",
                "partial-feature",
                "Partial-looking file names detected",
                "File names such as draft, wip, todo, or temp suggest incomplete implementation areas.",
                ConfidenceLevel.HEURISTIC_LOW,
                SeverityLevel.INFO,
                partial_hits[:8],
                partial_hits[:8],
            )
        )

    if readme_mentions:
        readme = readme_mentions[0]
        if "npm run" in readme and not any(item.name == "Node package" for item in build_markers):
            findings.append(
                _finding(
                    "SCN-007",
                    "doc-code-mismatch",
                    "README references Node commands without Node manifest",
                    "Documentation mentions `npm run` commands but KEEL did not find a matching `package.json` in the repo root scan.",
                    ConfidenceLevel.INFERRED_MEDIUM,
                    SeverityLevel.WARNING,
                    ["README.md"],
                    ["README.md"],
                )
            )

    return ScanArtifact(
        artifact_id=f"scan-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}",
        created_at=datetime.now().astimezone(),
        repo_root=str(root),
        stats=stats,
        languages=language_items,
        build_systems=build_markers,
        runtime_surfaces=list(runtime_surfaces.values()),
        entrypoints=entrypoints,
        modules=modules,
        tests=tests,
        configs=configs,
        contracts=contracts,
        findings=findings,
    )
