"""Shared router type aliases and registration structures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias, TypeVar

from agent_hooks.middleware import HookMiddleware
from agent_hooks.models.events import HookEvent
from agent_hooks.models.schemas.processing import HookProcessingResult
from agent_hooks.models.schemas.responses import HookResponseProtocol

EventModelT = TypeVar("EventModelT", bound=HookEvent)
HandlerResult: TypeAlias = HookProcessingResult | HookResponseProtocol | None
RouteHandler: TypeAlias = Callable[..., HandlerResult]
RouteDecorator: TypeAlias = Callable[[RouteHandler], RouteHandler]
MiddlewareDecorator: TypeAlias = Callable[[HookMiddleware], HookMiddleware]


@dataclass(frozen=True)
class InjectedArgument:
    """Store one handler parameter that should receive an injected value."""

    parameter_name: str
    value_kind: str


@dataclass(frozen=True)
class RouteDefinition:
    """Store one registered callback route."""

    event_factory: Callable[..., HookEvent]
    handler: RouteHandler
    injected_arguments: tuple[InjectedArgument, ...]


__all__ = [
    "EventModelT",
    "HandlerResult",
    "InjectedArgument",
    "MiddlewareDecorator",
    "RouteDefinition",
    "RouteDecorator",
    "RouteHandler",
]
