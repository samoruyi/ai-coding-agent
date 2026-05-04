"""FastAPI entrypoint for the Slack gateway."""

from __future__ import annotations

import logging
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .config import GatewaySettings, get_settings
from .slack_app import build_slack_handler
from .temporal_client import TemporalGateway

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _configure_logging(level: str) -> None:
    """Configure stdlib logging for stdout."""
    logging.basicConfig(level=level.upper(), format=_LOG_FORMAT, stream=sys.stdout)


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    """Construct the FastAPI app; ``settings`` may be injected for tests."""
    settings = settings or get_settings()
    _configure_logging(settings.log_level)
    log = logging.getLogger(__name__)
    log.info(
        "starting slack gateway: temporal=%s ns=%s queue=%s",
        settings.temporal_address,
        settings.temporal_namespace,
        settings.temporal_task_queue,
    )

    app = FastAPI(title="Coding Agent Slack Gateway", version="0.1.0")
    gateway = TemporalGateway(settings)
    slack_handler = build_slack_handler(settings, gateway)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        try:
            await gateway.get_client()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"status": "not_ready", "error": str(exc)}, status_code=503)
        return JSONResponse({"status": "ready"})

    @app.post("/slack/events")
    async def slack_events(req: Request) -> Response:
        return await slack_handler.handle(req)

    return app


def main() -> None:
    """Synchronous entrypoint exposed via the ``slack-gateway`` script."""
    settings = get_settings()
    uvicorn.run(
        "slack_gateway.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104
        port=settings.slack_gateway_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
