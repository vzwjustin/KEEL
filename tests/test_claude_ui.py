from __future__ import annotations

from datetime import datetime

from keel.session import build_claude_context, build_claude_system_message


def test_claude_system_message_uses_plain_words_for_common_blockers(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    alerts_path = repo / ".keel" / "session" / "alerts.yaml"
    alerts_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone().isoformat()
    alerts_path.write_text(
        "alerts:\n"
        "  - alert_id: ALT-plan\n"
        "    key: plan\n"
        "    source: validation\n"
        "    rule: KEE-VAL-003\n"
        "    summary: No active plan exists for the current goal.\n"
        "    detail: No active plan exists for the current goal.\n"
        "    severity: error\n"
        "    confidence: deterministic\n"
        f"    first_seen_at: '{now}'\n"
        f"    last_seen_at: '{now}'\n"
        "    count: 1\n"
        "    evidence:\n"
        "      - keel/specs/plans\n"
        "    next_action: make a plan first\n",
        encoding="utf-8",
    )

    system_message = build_claude_system_message(repo)

    assert system_message is not None


def test_claude_context_returns_alert_summary(fixture_repo) -> None:
    repo = fixture_repo("messy_repo")
    alerts_path = repo / ".keel" / "session" / "alerts.yaml"
    alerts_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone().isoformat()
    alerts_path.write_text(
        "alerts:\n"
        "  - alert_id: ALT-drift\n"
        "    key: drift\n"
        "    source: drift\n"
        "    rule: KEE-DRF-001\n"
        "    summary: Session drift detected.\n"
        "    detail: Files changed after checkpoint.\n"
        "    severity: warning\n"
        "    confidence: deterministic\n"
        f"    first_seen_at: '{now}'\n"
        f"    last_seen_at: '{now}'\n"
        "    count: 1\n"
        "    evidence:\n"
        "      - src/main.py\n"
        "    next_action: checkpoint or replan\n",
        encoding="utf-8",
    )

    context = build_claude_context(repo)
    assert "KEEL active alerts:" in context
