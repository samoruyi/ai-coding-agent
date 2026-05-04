"""Temporal worker entrypoint."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

from temporalio.client import Client, TLSConfig
from temporalio.worker import Worker

from .activities import (
    cleanup_workspace,
    clone_repo,
    commit_and_open_pr,
    post_slack_message,
    run_agent,
    setup_workspace,
)
from .config import WorkerSettings, get_settings
from .workflows import CodingAgentWorkflow

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _configure_logging(level: str) -> None:
    """Configure stdlib logging for stdout."""
    logging.basicConfig(level=level.upper(), format=_LOG_FORMAT, stream=sys.stdout)


def _build_tls(settings: WorkerSettings) -> TLSConfig | None:
    """Build a Temporal TLS config or return ``None`` for plain TCP."""
    if not settings.temporal_tls:
        return None
    if not settings.temporal_tls_cert_path or not settings.temporal_tls_key_path:
        raise RuntimeError(
            "TEMPORAL_TLS=true requires TEMPORAL_TLS_CERT_PATH and TEMPORAL_TLS_KEY_PATH"
        )
    return TLSConfig(
        client_cert=settings.temporal_tls_cert_path.read_bytes(),
        client_private_key=settings.temporal_tls_key_path.read_bytes(),
    )


def _install_shutdown_handlers(loop: asyncio.AbstractEventLoop, stop: asyncio.Event) -> None:
    """Wire SIGINT/SIGTERM to a single ``stop`` event for graceful shutdown."""

    def _on_signal(signame: str) -> None:
        logging.getLogger(__name__).info("received %s; initiating graceful shutdown", signame)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        # Windows event loops don't support add_signal_handler.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _on_signal, sig.name)


async def _run() -> None:
    settings = get_settings()
    _configure_logging(settings.log_level)
    log = logging.getLogger(__name__)
    log.info(
        "starting worker: address=%s namespace=%s queue=%s github_mode=%s model=%s",
        settings.temporal_address,
        settings.temporal_namespace,
        settings.temporal_task_queue,
        settings.github_mode,
        settings.agent_model,
    )

    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        tls=_build_tls(settings),
    )

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[CodingAgentWorkflow],
        activities=[
            setup_workspace,
            clone_repo,
            run_agent,
            commit_and_open_pr,
            post_slack_message,
            cleanup_workspace,
        ],
        max_concurrent_activities=settings.worker_max_concurrent_activities,
        max_concurrent_workflow_tasks=settings.worker_max_concurrent_workflow_tasks,
    )

    stop = asyncio.Event()
    _install_shutdown_handlers(asyncio.get_running_loop(), stop)

    async with worker:
        log.info("worker ready; polling task queue %s", settings.temporal_task_queue)
        await stop.wait()
    log.info("worker shut down cleanly")


def main() -> None:
    """Synchronous entrypoint exposed via the ``temporal-worker`` script."""
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run())


if __name__ == "__main__":
    main()
