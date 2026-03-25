from __future__ import annotations

from pathlib import Path

from keel.core.paths import resolve_paths
from keel.session.alerts import load_active_alerts
from keel.session.companion import companion_status


def _short(text: str, limit: int = 72) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _vibe(summary: str) -> str:
    s = summary.lower()
    if "no active plan" in s:
        return "needs plan"
    if "no active goal" in s:
        return "needs goal"
    if "next step" in s and "missing" in s:
        return "pick next step"
    if "delta" in s and "missing" in s:
        return "needs delta"
    if "question" in s and "open" in s:
        return "open question"
    if "drift" in s:
        return "drifting"
    return _short(summary, 40)


def build_statusline_text(repo_root: Path) -> str:
    paths = resolve_paths(repo_root)
    alerts = load_active_alerts(paths, limit=5)
    companion = companion_status(paths)
    alive = companion.get("fresh", False)

    severities = [a.get("severity", "warning") for a in alerts]
    blockers = sum(1 for s in severities if s in {"error", "blocker"})
    top = alerts[0] if alerts else None

    has_drift = any(
        a.get("source") == "drift" or "drift" in a.get("summary", "").lower()
        for a in alerts
    )

    if not alerts:
        state = "\033[32mon track\033[0m"
    elif blockers and top:
        state = "\033[31m" + _vibe(top.get("summary", "blocked")) + "\033[0m"
    elif top:
        state = "\033[33m" + _vibe(top.get("summary", "heads up")) + "\033[0m"
    else:
        state = "\033[32mon track\033[0m"

    if has_drift:
        drift_vis = "\033[33m~ drifting\033[0m"
    else:
        drift_vis = "\033[32m= on course\033[0m"

    companion_vis = "\033[32m\u25cf companion\033[0m" if alive else "\033[2m\u25cb companion\033[0m"
    return f"{state} \u2502 {drift_vis} \u2502 {companion_vis}"


def _load_open_questions(paths) -> list[dict]:
    from keel.session.service import SessionService
    return SessionService(paths).load_unresolved_questions()


def _format_question_instruction(questions: list[dict]) -> str:
    """Build an instruction block that tells Claude to use AskUserQuestion."""
    if not questions:
        return ""
    lines = [
        "KEEL has open questions. Present them to the user NOW using the AskUserQuestion tool.",
        "Use selectable options (2-4 per question). Make options concise and actionable.",
        "After the user answers, write answers back to KEEL with: keel goal --success-criterion or keel delta.",
        "",
        "Questions to present:",
    ]
    for q in questions[:4]:  # AskUserQuestion max 4
        lines.append(f"- Q: {q.get('question', '')}")
        why = q.get("why_it_matters", "")
        if why:
            lines.append(f"  Why: {why}")
        triggered = q.get("triggered_by", "")
        if triggered:
            lines.append(f"  Triggered by: {triggered}")
    return "\n".join(lines)


def build_claude_context(repo_root: Path) -> str:
    paths = resolve_paths(repo_root)
    alerts = load_active_alerts(paths, limit=3)
    brief = paths.current_brief_file.read_text(encoding="utf-8") if paths.current_brief_file.exists() else ""
    lines = []
    if brief:
        lines.append("KEEL brief:")
        lines.extend(line for line in brief.splitlines()[:8] if line.strip())
    if alerts:
        lines.append("KEEL active alerts:")
        for alert in alerts:
            lines.append(
                f"- [{alert.get('severity')}/{alert.get('confidence')}] "
                f"{alert.get('summary')} | rule={alert.get('rule')} | next={alert.get('next_action')}"
            )
    # Only present questions interactively after wizard is complete (goal + plan exist)
    try:
        from keel.session.service import SessionService
        session = SessionService(paths).load()
        has_plan = bool(session.active_plan_id)
        wizard_done = has_plan
        if wizard_done:
            questions = _load_open_questions(paths)
            if questions:
                lines.append("")
                lines.append(_format_question_instruction(questions))
    except Exception:
        pass
    return "\n".join(lines).strip()


def build_claude_system_message(repo_root: Path) -> str | None:
    paths = resolve_paths(repo_root)
    # Check for pending drift notification first (one-shot, consumed on read)
    notification = consume_pending_notification(paths)
    if notification:
        return notification
    alerts = load_active_alerts(paths, limit=3)
    if not alerts:
        return None
    top = alerts[0]
    hint = _vibe(top.get("summary", ""))
    return f"KEEL — {hint}"


def consume_pending_notification(paths) -> str | None:
    """Read and delete the one-shot notification file from companion."""
    from keel.core.artifacts import load_yaml
    nf = paths.pending_notification_file
    if not nf.exists():
        return None
    try:
        data = load_yaml(nf)
        nf.unlink(missing_ok=True)
    except OSError:
        return None
    if not data:
        return None
    msg = data.get("message", "drifting")
    return f"KEEL — you're {msg}, heads up"
