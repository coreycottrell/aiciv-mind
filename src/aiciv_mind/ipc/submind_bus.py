"""
aiciv_mind.ipc.submind_bus — ZeroMQ DEALER socket for a sub-mind.

Each sub-mind connects to the primary's ROUTER with its mind_id set as the
ZMQ IDENTITY. This lets the ROUTER route replies back to the correct DEALER
without the sub-mind including its own identity in outbound frames.

Wire envelope (DEALER perspective):
  Send: [b"", json_bytes]          — empty delimiter + payload
  Recv: [b"", json_bytes]          — ZMQ strips the ROUTER-prepended identity
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


class SubMindBus:
    """
    DEALER socket used by a sub-mind to communicate with the primary.

    The DEALER sets its ZMQ IDENTITY to mind_id before connecting. This identity
    is used by the ROUTER to route incoming frames to this specific DEALER without
    requiring the sub-mind to include routing headers.

    Usage::

        bus = SubMindBus("research-lead")
        bus.connect()
        bus.on(MsgType.TASK, handle_task)
        bus.on(MsgType.SHUTDOWN, handle_shutdown)
        bus.start_recv()

        reply = MindMessage.result("research-lead", "primary", task_id, summary)
        await bus.send(reply)

        bus.close()
    """

    def __init__(
        self,
        mind_id: str,
        router_path: str = "ipc:///tmp/aiciv-mind-router.ipc",
    ) -> None:
        self.mind_id = mind_id
        self._router_path = router_path
        self._ctx = zmq.asyncio.Context()
        self._dealer: zmq.asyncio.Socket = self._ctx.socket(zmq.DEALER)
        # Set ZMQ identity so the ROUTER knows who this DEALER is.
        self._dealer.setsockopt(zmq.IDENTITY, mind_id.encode("utf-8"))
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._recv_task: asyncio.Task | None = None
        self._running = False

    def connect(self) -> None:
        """Connect to the primary's ROUTER socket. Must be called before recv_loop."""
        self._dealer.connect(self._router_path)
        logger.debug("SubMindBus(%s) connected to %s", self.mind_id, self._router_path)

    def on(
        self,
        msg_type: str,
        handler: Callable[["MindMessage"], Awaitable[None]],
    ) -> None:
        """Register an async handler for a message type."""
        self._handlers[msg_type].append(handler)

    async def send(self, msg: MindMessage) -> None:
        """
        Send a message to the primary (or whoever is on the ROUTER end).

        Frame layout sent: [b"", json_bytes]
        The empty delimiter is required by the DEALER/ROUTER protocol.
        """
        await self._dealer.send_multipart([b"", msg.to_bytes()])
        logger.debug(
            "SubMindBus(%s) sent %s to %s (msg_id=%s)",
            self.mind_id,
            msg.type,
            msg.recipient,
            msg.id,
        )

    async def recv_loop(self) -> None:
        """
        Receive loop. Runs until close() is called.

        Frame layout received: [b"", json_bytes]
        The ZMQ layer strips the ROUTER-prepended identity frame before delivery.
        Dispatches each message to all registered handlers for its type.
        """
        self._running = True
        logger.debug("SubMindBus(%s) recv_loop started", self.mind_id)
        while self._running:
            try:
                frames = await self._dealer.recv_multipart()
                # DEALER recv: [delimiter, payload] — at minimum 2 frames
                if len(frames) < 2:
                    logger.warning(
                        "SubMindBus(%s): unexpected frame count %d (expected >= 2)",
                        self.mind_id,
                        len(frames),
                    )
                    continue
                # Payload is always the last frame regardless of extra routing frames.
                json_bytes = frames[-1]
                msg = MindMessage.from_bytes(json_bytes)
                logger.debug(
                    "SubMindBus(%s) received %s from %s (msg_id=%s)",
                    self.mind_id,
                    msg.type,
                    msg.sender,
                    msg.id,
                )
                for handler in self._handlers.get(msg.type, []):
                    asyncio.create_task(handler(msg))
            except zmq.ZMQError as exc:
                if self._running:
                    logger.error(
                        "SubMindBus(%s) ZMQ error in recv_loop: %s", self.mind_id, exc
                    )
                break
            except Exception as exc:
                logger.error(
                    "SubMindBus(%s) error in recv_loop: %s",
                    self.mind_id,
                    exc,
                    exc_info=True,
                )

    def start_recv(self) -> asyncio.Task:
        """Start recv_loop as a background asyncio Task and return it."""
        self._recv_task = asyncio.create_task(self.recv_loop())
        return self._recv_task

    def close(self) -> None:
        """Stop the recv loop and close the DEALER socket and ZMQ context."""
        self._running = False
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
        self._dealer.close(linger=0)
        self._ctx.term()
        logger.debug("SubMindBus(%s) closed", self.mind_id)
