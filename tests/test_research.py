from __future__ import annotations

from typer.testing import CliRunner

from keel.cli.app import app


def test_research_keeps_external_guidance_separate(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    config_path = repo / ".keel" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "strictness: standard\nresearch_enabled: true\nresearch_timeout_seconds: 2\nmax_scan_files: 4000\nignored_directories: []\nauthoritative_config_names: [pyproject.toml]\noutput_format: text\n",
        encoding="utf-8",
    )
    source = repo / "notes.txt"
    source.write_text("Official design note placeholder", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--repo", str(repo), "--json", "research", "--source", str(source)],
    )

    assert result.exit_code == 0, result.stdout
    assert '"record_kind": "external-guidance"' in result.stdout
    assert '"source_trust": "local-file"' in result.stdout
