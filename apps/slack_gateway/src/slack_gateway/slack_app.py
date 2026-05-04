"""Slack Bolt app: HMAC verification + ``app_mention`` routing."""

from __future__ import annotations

import logging
import re
from typing import Any

from coding_agent_shared import AgentRequest, SlackContext
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp

from .config import GatewaySettings
from .temporal_client import TemporalGateway

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"<@U[A-Z0-9]+>\s*")
_FALLBACK_TEAM_ID = "T_UNKNOWN"
_FALLBACK_USER_ID = "U_UNKNOWN"
_PLACEHOLDER_BOT_TOKEN = "xoxb-placeholder"  # noqa: S105 - dev-only stub, never used in prod
_PLACEHOLDER_SIGNING_SECRET = "placeholder"  # noqa: S105 - dev-only stub


def build_slack_handler(
    settings: GatewaySettings, gateway: TemporalGateway
) -> AsyncSlackRequestHandler:
    """Wire a Bolt ``AsyncApp`` to FastAPI and return the request handler."""
    if not settings.slack_signing_secret:
        logger.warning("SLACK_SIGNING_SECRET is empty; /slack/events will reject all requests")

    app = AsyncApp(
        token=settings.slack_bot_token or _PLACEHOLDER_BOT_TOKEN,
        signing_secret=settings.slack_signing_secret or _PLACEHOLDER_SIGNING_SECRET,
        request_verification_enabled=bool(settings.slack_signing_secret),
    )

    @app.event("app_mention")
    async def on_app_mention(body: dict[str, Any], ack) -> None:
        # ack() must return within 3s of the inbound request.
        await ack()
        try:
            await _handle_mention(body, settings, gateway)
        except Exception:  # noqa: BLE001
            logger.exception("failed to handle app_mention")

    return AsyncSlackRequestHandler(app)


async def _handle_mention(
    body: dict[str, Any], settings: GatewaySettings, gateway: TemporalGateway
) -> None:
    """Translate the Slack event into an ``AgentRequest`` and submit it to Temporal."""
    event: dict[str, Any] = body.get("event") or {}
    text = _strip_mention(event.get("text", ""))
    if not text:
        return

    team_id = body.get("team_id") or event.get("team") or _FALLBACK_TEAM_ID
    channel_id = event.get("channel", "")
    thread_ts = event.get("thread_ts") or event.get("ts")
    user_id = event.get("user", _FALLBACK_USER_ID)

    if not channel_id or not thread_ts:
        logger.warning("missing channel_id/thread_ts; dropping event: %s", event)
        return

    request = AgentRequest(
        prompt=text,
        repo_owner=settings.github_default_owner,
        repo_name=settings.github_default_repo,
        slack=SlackContext(
            team_id=team_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            user_id=user_id,
        ),
    )

    workflow_id, action = await gateway.start_or_signal(request)
    logger.info("slack mention -> workflow %s (%s)", workflow_id, action.value)


def _strip_mention(text: str) -> str:
    """Strip the ``<@Uxxxx>`` user mention from the start of the prompt."""
    return _MENTION_RE.sub("", text or "").strip()
