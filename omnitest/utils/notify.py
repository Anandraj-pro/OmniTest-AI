"""Outbound notifications. Currently: Slack incoming webhooks.

Configure with OMNI_SLACK_WEBHOOK_URL (see .env). If it's unset, `notify_slack`
is a safe no-op — code can call it unconditionally.
"""
from __future__ import annotations

import httpx

from omnitest.config import settings
from omnitest.utils.logger import get_logger

log = get_logger("notify")


def notify_slack(text: str, *, blocks: list[dict] | None = None,
                 webhook_url: str | None = None, timeout: float = 10.0) -> bool:
    """Post a message to a Slack incoming webhook. Returns True on success.

    `text` is always sent as the notification fallback (shown in previews and
    when blocks can't render). `blocks` optionally carries Block Kit layout
    (sections, buttons). No-op (returns False) when no webhook is configured,
    and never raises — alerting must not crash the job it's reporting on.
    """
    url = webhook_url or settings.slack_webhook_url
    if not url:
        log.debug("Slack webhook not configured; skipping notification.")
        return False
    payload: dict = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 — alerting is best-effort
        log.warning("Slack notification failed: %s", exc)
        return False


def allure_button(label: str = "Open Allure Report", *,
                  style: str | None = None) -> dict | None:
    """A Block Kit link-button to the published Allure report, or None if the
    report base URL isn't configured (Slack rejects buttons without an http URL).
    """
    url = settings.report_base_url
    if not (url.startswith("http://") or url.startswith("https://")):
        return None
    btn: dict = {"type": "button", "url": url,
                 "text": {"type": "plain_text", "text": label, "emoji": True}}
    if style:
        btn["style"] = style
    return {"type": "actions", "elements": [btn]}
