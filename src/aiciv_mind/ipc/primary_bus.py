"""
aiciv_mind.ipc.primary_bus — ZeroMQ ROUTER socket for the primary mind.

The primary mind binds a ROUTER socket. Each sub-mind connects as a DEALER
with its mind_id set as the ZMQ identity. The ROUTER uses these identities
to route messages to the correct sub-mind.

Wire envelope (ROUTER perspective):
  Send: [identity_bytes, b"", json_bytes]
  Recv: [identity_bytes, b"", json_bytes]  — ZMQ prepends identity automatically
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable

import zmq
import zmq.asyncio

from aiciv_mind.ipc.messages import MindMessage

logger = logging.getLogger(__name__)


class PrimaryBus:
    """
    ROUTER socket bound by the primary mind.

    Sub-minds connect to this bus as DEALERs with their mind_id as ZMQ identity.
    The ROUTER automatically demultiplexes incoming frames by identity, enabling
    the primary to address any sub-mind by its mind_id string.

    Usage::

        bus = PrimaryBus()
        bus.bind()
        bus.on(MsgType.RESULT, handle_result)
        bus.on(MsgType.SHUTDOWN_ACK, handle_shutdown_ack)
        bus.start_recv()

        msg = MindMessage.task("primary", "research-lead", task_id, objective)
        await bus.send(msg)

        # When done:
        bus.close()
    """

    DEFAULT_PATH = "ipc:///tmp/aiciv-mind-router.ipc"

    def __init__(self, router_path: str = DEFAULT_PATH) -> None:
        self._router_path = router_path
        self._ctx = zmq.asyncio.Context()
        self._router: zmq.asyncio.Socket = self._ctx.socket(zmq.ROUTER)
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._recv_task: asyncio.Task | None = None
        self._running = False

    def bind(self) -> None:
        """Bind the ROUTER socket. Must be called before recv_loop or start_recv."""
        self._router.bind(self._router_path)
        logger.debug("PrimaryBus bound to %s", self._router_path)

    def on(
        self,
        msg_type: str,
        handler: Callable[["MindMessage"], Awaitable[None]],
    ) -> None:
        """Register an async handler for a message type. Multiple handlers per type are supported."""
        self._handlers[msg_type].append(handler)

    async def send(self, msg: MindMessage) -> None:
        """
        Send a message to a specific sub-mind.

        Routes by msg.recipient, which must match the DEALER's ZMQ identity
        (i.e., the sub-mind's mind_id).

        Frame layout sent: [identity_bytes, b"", json_bytes]
        """
        identity = msg.recipient.encode("utf-8")
        await self._router.send_multipart([identity, b"", msg.to_bytes()])
        logger.debug(
            "PrimaryBus sent %s to %s (msg_id=%s)",
            msg.type,
            msg.recipient,
            msg.id,
        )

    async def recv_loop(self) -> None:
        """
        Receive loop. Runs until close() is called.

        Frame layout received: [identity, b"", json_bytes]
        Dispatches each message to all registered handlers for its type.
        Handler exceptions are logged but do not stop the loop.
        """
        self._running = True
        logger.debug("PrimaryBus recv_loop started")
        while self._running:
            try:
                frames = await self._router.recv_multipart()
                # ROUTER recv: [identity, delimiter, payload]
                if len(frames) < 3:
                    logger.warning(
                        "PrimaryBus: unexpected frame count %d (expected 3)", len(frames)
                    )
                    continue
                json_bytes = frames[2]
                msg = MindMessage.from_bytes(json_bytes)
                logger.debug(
                    "PrimaryBus received %s from %s (msg_id=%s)",
                    msg.type,
                    msg.sender,
                    msg.id,
                )
                for handler in self._handlers.get(msg.type, []):
                    asyncio.create_task(handler(msg))
            except zmq.ZMQError as exc:
                if self._running:
                    logger.error("PrimaryBus ZMQ error in recv_loop: %s", exc)
                break
            except Exception as exc:
                logger.error("PrimaryBus error in recv_loop: %s", exc, exc_info=True)

    def start_recv(self) -> asyncio.Task:
        """Start recv_loop as a background asyncio Task and return it."""
        self._recv_task = asyncio.create_task(self.recv_loop())
        return self._recv_task

    def close(self) -> None:
        """Stop the recv loop and close the ROUTER socket and ZMQ context."""
        self._running = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
        self._router.close(linger=0)
        self._ctx.term()
        logger.debug("PrimaryBus closed")
