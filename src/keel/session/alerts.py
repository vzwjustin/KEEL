from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from keel.core.artifacts import load_yaml, save_yaml
from keel.core.paths import KeelPaths, now_iso
from keel.models import DriftArtifact, ValidationArtifact


ALERT_WINDOW_MINUTES = 20
MAX_ALERTS = 25


def _load_alerts(paths: KeelPaths) -> list[dict]:
    payload = load_yaml(paths.alerts_file)
    return payload.get("alerts", [])


def load_active_alerts(paths: KeelPaths, limit: int = 5) -> list[dict]:
    alerts = _load_alerts(paths)
    cutoff = datetime.now().astimezone() - timedelta(minutes=ALERT_WINDOW_MINUTES)
    active = []
    for alert in alerts:
        raw = alert.get("last_seen_at")
        try:
            last_seen = datetime.fromisoformat(raw) if raw else cutoff
        except ValueError:
            last_seen = cutoff
        if last_seen >= cutoff:
            active.append(alert)
    return active[-limit:]


def _upsert_alert(alerts: list[dict], item: dict) -> None:
    for alert in alerts:
        if alert.get("key") == item["key"]:
            alert["last_seen_at"] = item["last_seen_at"]
            alert["count"] = int(alert.get("count", 1)) + 1
            alert["evidence"] = item["evidence"]
            alert["summary"] = item["summary"]
            alert["detail"] = item["detail"]
            alert["next_action"] = item["next_action"]
            return
    alerts.append(item)


def update_alert_feed(
    *,
    paths: KeelPaths,
    drift: DriftArtifact,
    validation: ValidationArtifact,
) -> list[dict]:
    now = now_iso()
    alerts = _load_alerts(paths)
    for finding in drift.findings:
        if finding.severity.value == "info":
            continue
        key = hashlib.sha1(f"drift:{finding.code}:{finding.layer}:{finding.summary}".encode("utf-8")).hexdigest()[:12]
        _upsert_alert(
            alerts,
            {
                "alert_id": f"ALT-{key}",
                "key": key,
                "source": "drift",
                "rule": finding.code,
                "summary": finding.summary,
                "detail": finding.detail,
                "severity": finding.severity.value,
                "confidence": finding.confidence.value,
                "first_seen_at": now,
                "last_seen_at": now,
                "count": 1,
                "evidence": finding.evidence[:6],
                "next_action": finding.suggested_action,
            },
        )
    for finding in validation.findings:
        if finding.severity.value not in {"warning", "error", "blocker"}:
            continue
        key = hashlib.sha1(f"validation:{finding.code}:{finding.message}".encode("utf-8")).hexdigest()[:12]
        _upsert_alert(
            alerts,
            {
                "alert_id": f"ALT-{key}",
                "key": key,
                "source": "validation",
                "rule": finding.code,
                "summary": finding.message,
                "detail": finding.suggested_action,
                "severity": finding.severity.value,
                "confidence": finding.confidence.value,
                "first_seen_at": now,
                "last_seen_at": now,
                "count": 1,
                "evidence": finding.paths[:6],
                "next_action": finding.suggested_action,
            },
        )
    save_yaml(paths.alerts_file, {"alerts": alerts[-MAX_ALERTS:]})
    return load_active_alerts(paths, limit=5)
