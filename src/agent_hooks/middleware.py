"""Execute middleware around hook dispatch."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from agent_hooks.models import HookInput, HookPayload, HookProcessingResult
from agent_hooks.transport import DisplayTransport


@dataclass(frozen=True)
class HookMiddlewareContext:
    """Store the context passed through the middleware chain."""

    input_data: HookInput
    transport: DisplayTransport

    @property
    def payload(self) -> HookPayload:
        """Return the parsed hook payload for this middleware stage."""
        return self.input_data.payload


NextMiddleware: TypeAlias = Callable[[HookMiddlewareContext], HookProcessingResult]
FinalHandler: TypeAlias = Callable[[HookInput, DisplayTransport], HookProcessingResult]


class HookMiddleware(Protocol):
    """Define the middleware interface used by hook dispatch."""

    def __call__(
        self,
        context: HookMiddlewareContext,
        call_next: NextMiddleware,
    ) -> HookProcessingResult:
        """Process one middleware stage and optionally short-circuit dispatch."""
        ...


def dispatch_with_middlewares(
    input_data: HookInput,
    transport: DisplayTransport,
    *,
    middlewares: Sequence[HookMiddleware],
    final_handler: FinalHandler,
) -> HookProcessingResult:
    """Run one handler through the configured middleware chain."""
    context = HookMiddlewareContext(input_data=input_data, transport=transport)
    middleware_chain = tuple(middlewares)

    def invoke(index: int, current_context: HookMiddlewareContext) -> HookProcessingResult:
        if index >= len(middleware_chain):
            return final_handler(current_context.input_data, current_context.transport)

        middleware = middleware_chain[index]
        return middleware(
            current_context,
            lambda next_context: invoke(index + 1, next_context),
        )

    return invoke(0, context)
