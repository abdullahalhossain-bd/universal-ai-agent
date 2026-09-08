"""
Best-effort alerting for events that need a human, not just a log line.

No external monitoring vendor is wired in (no Sentry/Datadog SDK,
no hard dependency) — instead this posts a small JSON payload to
`settings.alert_webhook_url` if one is configured. That URL can point
at a Slack incoming webhook, a PagerDuty/Opsgenie inbound integration,
or your own endpoint — all of those accept a simple JSON POST, so no
vendor SDK is required to get paged.

If `alert_webhook_url` is unset, `send_alert` is a no-op: unhandled
errors still land in the structured logs (see app/core/logging_config.py)
and are still visible to any log-based alerting you already have (e.g.
a CloudWatch metric filter on `"level":"ERROR"`). This function is an
additional, optional push channel — never the only place an error is
recorded.

Never raises: alerting must not become a second way for a request to
fail. Call it from a background task (see main.py) so a slow or down
webhook endpoint never adds latency to the response the user is
waiting on.
"""

import logging

import httpx

from app.core.config import settings
from app.core.request_context import get_request_id


logger = logging.getLogger("app.alerting")


async def send_alert(
    *,
    title: str,
    detail: str,
    extra: dict | None = None,
) -> None:

    if not settings.alert_webhook_url:
        return

    payload = {
        "title": title,
        "detail": detail,
        "request_id": get_request_id(),
        "environment": settings.environment,
        **(extra or {}),
    }

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(
                settings.alert_webhook_url,
                json=payload,
            )
            if resp.status_code >= 400:
                logger.error(
                    "Alert webhook returned %s",
                    resp.status_code,
                    extra={"alert_title": title},
                )
    except Exception:
        # An alerting failure must never surface to the request
        # that triggered it, and must never become an unhandled
        # exception itself — just log it and move on.
        logger.error(
            "Failed to deliver alert webhook",
            exc_info=True,
            extra={"alert_title": title},
        )
