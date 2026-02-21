"""
OrQuanta Agentic v1.0 — WebSocket Agent Reasoning Stream

Real-time streaming of agent reasoning steps to the frontend dashboard.
Clients subscribe to a WebSocket at /ws/agent-stream and receive
live JSON messages as agents think, act, and observe.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("orquanta.ws")
router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"WebSocket connected. Total clients: {len(self._connections)}")

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info(f"WebSocket disconnected. Remaining clients: {len(self._connections)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a JSON message to all connected clients."""
        data = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to(self, ws: WebSocket, message: dict[str, Any]) -> None:
        """Send a message to a specific client."""
        try:
            await ws.send_text(json.dumps(message))
        except Exception as exc:
            logger.warning(f"Failed to send WS message: {exc}")
            self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


# Module-level manager (shared across the app)
manager = ConnectionManager()


@router.websocket("/ws/agent-stream")
async def agent_stream(ws: WebSocket) -> None:
    """WebSocket endpoint for live agent reasoning feed.
    
    Message types sent by server:
    - agent_status: Agent state change (idle/thinking/acting)
    - reasoning_step: One ReAct step (REASON/ACT/OBSERVE)
    - goal_update: Goal status changed
    - metrics_tick: Periodic platform metrics snapshot
    - alert: Safety or cost alert
    - heartbeat: Keep-alive every 30s
    
    Messages received from client:
    - {"type": "subscribe", "goal_id": "..."}  — subscribe to a specific goal
    - {"type": "ping"}                          — keep-alive ping
    """
    await manager.connect(ws)
    subscribed_goal: str | None = None

    # Send welcome message
    await manager.send_to(ws, {
        "type": "connected",
        "message": "OrQuanta Agent Stream connected. Agents are active.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Start metrics ticker task
    ticker_task = asyncio.create_task(_metrics_ticker(ws))

    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
                data = json.loads(raw)
                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await manager.send_to(ws, {"type": "pong", "ts": datetime.now(timezone.utc).isoformat()})

                elif msg_type == "subscribe":
                    subscribed_goal = data.get("goal_id")
                    await manager.send_to(ws, {
                        "type": "subscribed",
                        "goal_id": subscribed_goal,
                        "message": f"Subscribed to goal {subscribed_goal}",
                    })

                elif msg_type == "unsubscribe":
                    subscribed_goal = None
                    await manager.send_to(ws, {"type": "unsubscribed"})

            except asyncio.TimeoutError:
                # Send heartbeat if no message for 60s
                await manager.send_to(ws, {
                    "type": "heartbeat",
                    "clients": manager.client_count,
                    "ts": datetime.now(timezone.utc).isoformat(),
                })

    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
        manager.disconnect(ws)
    finally:
        ticker_task.cancel()


async def _metrics_ticker(ws: WebSocket) -> None:
    """Send periodic metrics updates to a connected client."""
    from ...agents.scheduler_agent import SchedulerAgent
    from ...agents.safety_governor import get_governor

    scheduler = SchedulerAgent()
    while True:
        try:
            await asyncio.sleep(5)
            queue = scheduler.get_queue_status()
            spend = get_governor().get_spend_summary()
            await manager.send_to(ws, {
                "type": "metrics_tick",
                "data": {
                    "active_jobs": queue.get("total_jobs", 0),
                    "queued_jobs": queue.get("queued_jobs", 0),
                    "active_instances": queue.get("active_bins", 0),
                    "daily_spend_usd": spend["daily_spend_usd"],
                    "emergency_stop": get_governor().is_stopped,
                },
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug(f"Metrics ticker error: {exc}")
            break


async def broadcast_reasoning_step(
    goal_id: str,
    agent_name: str,
    step: str,
    content: Any,
) -> None:
    """Helper: broadcast a reasoning step to all connected WebSocket clients.
    
    Call this from agents/orchestrator as they execute steps.
    """
    await manager.broadcast({
        "type": "reasoning_step",
        "goal_id": goal_id,
        "agent": agent_name,
        "step": step,
        "content": content,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


async def broadcast_agent_status(agent_name: str, status: str) -> None:
    """Broadcast an agent status change to all connected clients."""
    await manager.broadcast({
        "type": "agent_status",
        "agent": agent_name,
        "status": status,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


async def broadcast_alert(message: str, severity: str = "info") -> None:
    """Broadcast an alert to all connected clients."""
    await manager.broadcast({
        "type": "alert",
        "message": message,
        "severity": severity,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
