"""Thin wrapper around the Temporal client used by the Slack gateway."""

from __future__ import annotations

import asyncio
import logging
from enum import StrEnum

from coding_agent_shared import (
    AgentRequest,
    FollowUpSignal,
    workflow_id_for_thread,
)
from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDReusePolicy
from temporalio.service import RPCError, RPCStatusCode

from .config import GatewaySettings

logger = logging.getLogger(__name__)

WORKFLOW_TYPE_NAME = "CodingAgentWorkflow"
FOLLOW_UP_SIGNAL_NAME = "follow_up"


class GatewayAction(StrEnum):
    """Outcome of ``start_or_signal``."""

    STARTED = "started"
    SIGNALLED = "signalled"


class TemporalGateway:
    """Lazy Temporal client + ``start_or_signal`` helper."""

    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings
        self._client: Client | None = None
        self._lock = asyncio.Lock()

    async def get_client(self) -> Client:
        """Return the connected Temporal client, connecting on first use."""
        if self._client is not None:
            return self._client
        async with self._lock:
            if self._client is None:
                self._client = await Client.connect(
                    self._settings.temporal_address,
                    namespace=self._settings.temporal_namespace,
                )
                logger.info(
                    "connected to temporal at %s ns=%s",
                    self._settings.temporal_address,
                    self._settings.temporal_namespace,
                )
        return self._client

    async def start_or_signal(self, request: AgentRequest) -> tuple[str, GatewayAction]:
        """Start a new workflow for the Slack thread, or signal the running one.

        ``ALLOW_DUPLICATE`` lets a previously completed/failed workflow with
        the same deterministic id be replaced cleanly when the user revives
        a stale thread.
        """
        client = await self.get_client()
        workflow_id = workflow_id_for_thread(request.slack)
        handle = client.get_workflow_handle(workflow_id)

        if await _is_running(handle):
            await handle.signal(
                FOLLOW_UP_SIGNAL_NAME,
                FollowUpSignal(message=request.prompt, user_id=request.slack.user_id),
            )
            logger.info("signalled follow_up to %s", workflow_id)
            return workflow_id, GatewayAction.SIGNALLED

        await client.start_workflow(
            WORKFLOW_TYPE_NAME,
            request,
            id=workflow_id,
            task_queue=self._settings.temporal_task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
        )
        logger.info("started workflow %s", workflow_id)
        return workflow_id, GatewayAction.STARTED


async def _is_running(handle: WorkflowHandle) -> bool:
    """Return True iff the workflow exists *and* is currently RUNNING."""
    try:
        desc = await handle.describe()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            return False
        raise
    return bool(desc.status and desc.status.name == "RUNNING")
