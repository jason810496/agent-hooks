"""Provide the decorator-based router for agent hook callbacks."""

from __future__ import annotations

from agent_hooks.router.app import AgentHook
from agent_hooks.router.definitions import (
    EventModelT,
    HandlerResult,
    MiddlewareDecorator,
    RouteDecorator,
    RouteHandler,
)
from agent_hooks.router.request import CallbackRequest

__all__ = [
    "AgentHook",
    "CallbackRequest",
    "EventModelT",
    "HandlerResult",
    "MiddlewareDecorator",
    "RouteDecorator",
    "RouteHandler",
]
