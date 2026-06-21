"""The decorator-based hook router implementation."""

from __future__ import annotations

from typing import IO

from agent_hooks.config import RuntimeConfig
from agent_hooks.default_handlers import DefaultHookHandler, HookFallbackHandler
from agent_hooks.enums import HookEventName, HookProvider
from agent_hooks.middleware import HookMiddleware, dispatch_with_middlewares
from agent_hooks.models.events import (
    NotificationEvent,
    PermissionRequestEvent,
    PostToolUseEvent,
    SessionStartEvent,
    StopEvent,
    StopFailureEvent,
    UserPromptSubmitEvent,
)
from agent_hooks.models.schemas.hooks import HookInput
from agent_hooks.models.schemas.processing import HookProcessingResult
from agent_hooks.providers import provider_client
from agent_hooks.router.definitions import (
    EventModelT,
    MiddlewareDecorator,
    RouteDecorator,
    RouteDefinition,
    RouteHandler,
)
from agent_hooks.router.dispatch import (
    build_event_model,
    build_injected_arguments,
    call_route_handler,
    coerce_route_result,
    empty_processing_result,
)
from agent_hooks.router.request import CallbackRequest
from agent_hooks.transport import DisplayTransport


class _UnsetFallbackHandler:
    """Represent an omitted fallback handler constructor argument."""


_UNSET_FALLBACK_HANDLER = _UnsetFallbackHandler()


class AgentHook:
    """Register decorator-based callback handlers and dispatch hook events."""

    def __init__(
        self,
        *,
        fallback_handler: HookFallbackHandler | None | _UnsetFallbackHandler = (
            _UNSET_FALLBACK_HANDLER
        ),
        fallback_to_default_processor: bool | None = None,
        provider: HookProvider | str | None = None,
    ) -> None:
        """Initialize the hook router.

        :param fallback_handler: Handler used when no route is registered for an event.
        :type fallback_handler: HookFallbackHandler | None
        :param fallback_to_default_processor: Deprecated compatibility flag for the built-in
            fallback handler.
        :type fallback_to_default_processor: bool | None
        :param provider: Optional default provider for parsing and response rendering.
        :type provider: HookProvider | str | None
        :raises ValueError: If both fallback configuration styles are supplied.
        """
        self._fallback_handler = self._resolve_fallback_handler(
            fallback_handler=fallback_handler,
            fallback_to_default_processor=fallback_to_default_processor,
        )
        self._provider = HookProvider(provider) if isinstance(provider, str) else provider
        self._routes: dict[HookEventName, RouteDefinition] = {}
        self._middlewares: tuple[HookMiddleware, ...] = ()

    @property
    def provider(self) -> HookProvider | None:
        """Return the router's default provider, when configured."""
        return self._provider

    def notification(self) -> RouteDecorator[NotificationEvent]:
        """Register a handler for ``Notification`` events.

        :return: Decorator that stores the handler.
        """
        return self._register(HookEventName.NOTIFICATION, NotificationEvent)

    def permission(self) -> RouteDecorator[PermissionRequestEvent]:
        """Register a handler for normalized permission-request events.

        :return: Decorator that stores the handler.
        """
        return self._register(HookEventName.PERMISSION_REQUEST, PermissionRequestEvent)

    def pre_tool_use(self) -> RouteDecorator[PermissionRequestEvent]:
        """Register a handler for Codex ``PreToolUse`` events."""
        return self.permission()

    def middleware(self) -> MiddlewareDecorator:
        """Register one middleware for this hook router."""

        def decorator(middleware: HookMiddleware) -> HookMiddleware:
            self._middlewares = (*self._middlewares, middleware)
            return middleware

        return decorator

    def session_start(self) -> RouteDecorator[SessionStartEvent]:
        """Register a handler for ``SessionStart`` events."""
        return self._register(HookEventName.SESSION_START, SessionStartEvent)

    def user_prompt_submit(self) -> RouteDecorator[UserPromptSubmitEvent]:
        """Register a handler for ``UserPromptSubmit`` events."""
        return self._register(HookEventName.USER_PROMPT_SUBMIT, UserPromptSubmitEvent)

    def post_tool_use(self) -> RouteDecorator[PostToolUseEvent]:
        """Register a handler for ``PostToolUse`` events."""
        return self._register(HookEventName.POST_TOOL_USE, PostToolUseEvent)

    def stop(self) -> RouteDecorator[StopEvent]:
        """Register a handler for ``Stop`` events.

        :return: Decorator that stores the handler.
        """
        return self._register(HookEventName.STOP, StopEvent)

    def stop_failure(self) -> RouteDecorator[StopFailureEvent]:
        """Register a handler for ``StopFailure`` events.

        :return: Decorator that stores the handler.
        """
        return self._register(HookEventName.STOP_FAILURE, StopFailureEvent)

    def dispatch(self, input_data: HookInput, transport: DisplayTransport) -> HookProcessingResult:
        """Dispatch a parsed hook payload through the registered router.

        :param input_data: Parsed hook input.
        :type input_data: HookInput
        :param transport: Display transport used by the fallback handler.
        :type transport: DisplayTransport
        :return: Processing result used by logging and output emission.
        """
        if input_data.parse_error is not None:
            return empty_processing_result(error=input_data.parse_error)

        middlewares = (
            *provider_client.get_middlewares(input_data.payload.provider),
            *self._middlewares,
        )
        return dispatch_with_middlewares(
            input_data,
            transport,
            middlewares=middlewares,
            final_handler=self._dispatch_without_middlewares,
        )

    def _dispatch_without_middlewares(
        self,
        input_data: HookInput,
        transport: DisplayTransport,
    ) -> HookProcessingResult:
        """Dispatch a parsed payload after middleware has already run."""
        route = self._routes.get(input_data.payload.event_name)
        if route is None:
            if self._fallback_handler is not None:
                return self._process_hook(input_data, transport)
            return empty_processing_result()

        request = CallbackRequest(input_data=input_data)
        hook_event = route.event_factory(input_data.payload)
        result = call_route_handler(route, request, hook_event, transport)
        return coerce_route_result(result)

    def _process_hook(
        self,
        input_data: HookInput,
        transport: DisplayTransport,
    ) -> HookProcessingResult:
        """Process an unhandled hook payload with the built-in fallback behavior.

        :param input_data: Parsed hook input.
        :type input_data: HookInput
        :param transport: UI transport implementation.
        :type transport: DisplayTransport
        :return: Processing result for logging and emission.
        """
        error = input_data.parse_error
        if error is not None:
            return empty_processing_result(error=error)

        payload = input_data.payload
        handler = self._fallback_handler
        if handler is None:
            return empty_processing_result(error=error)
        return handler.handle(payload, transport, current_error=error)

    def _resolve_fallback_handler(
        self,
        *,
        fallback_handler: HookFallbackHandler | None | _UnsetFallbackHandler,
        fallback_to_default_processor: bool | None,
    ) -> HookFallbackHandler | None:
        """Return the effective fallback handler for this router.

        :param fallback_handler: Explicit fallback handler configuration.
        :type fallback_handler: HookFallbackHandler | None | _UnsetFallbackHandler
        :param fallback_to_default_processor: Deprecated compatibility flag.
        :type fallback_to_default_processor: bool | None
        :return: Effective fallback handler, or ``None`` when fallback is disabled.
        :raises ValueError: If both fallback configuration styles are supplied.
        """
        if not isinstance(fallback_handler, _UnsetFallbackHandler):
            if fallback_to_default_processor is not None:
                raise ValueError(
                    "Use fallback_handler or fallback_to_default_processor, not both."
                )
            return fallback_handler

        if fallback_to_default_processor is False:
            return None

        return DefaultHookHandler()

    def run_callback(
        self,
        *,
        stdin: IO[str] | None = None,
        stdout: IO[str] | None = None,
        runtime_config: RuntimeConfig | None = None,
        transport: DisplayTransport | None = None,
        provider: HookProvider | str | None = None,
    ) -> int:
        """Run the standard callback flow with this router instance.

        :param stdin: Optional stdin override.
        :type stdin: IO[str] | None
        :param stdout: Optional stdout override.
        :type stdout: IO[str] | None
        :param runtime_config: Optional runtime configuration override.
        :type runtime_config: RuntimeConfig | None
        :param transport: Optional UI transport override.
        :type transport: DisplayTransport | None
        :param provider: Optional provider override.
        :type provider: HookProvider | str | None
        :return: Process exit code.
        """
        from agent_hooks.runner import run_callback

        return run_callback(
            stdin=stdin,
            stdout=stdout,
            runtime_config=runtime_config,
            transport=transport,
            hook=self,
            provider=provider or self._provider,
        )

    def _register(
        self,
        event_name: HookEventName,
        event_model: type[EventModelT],
    ) -> RouteDecorator[EventModelT]:
        """Register one routed event handler.

        :param event_name: Hook event to bind.
        :type event_name: HookEventName
        :param event_model: Typed payload model passed to the handler.
        :type event_model: type[EventModelT]
        :return: Decorator that stores the handler.
        """

        def decorator(handler: RouteHandler) -> RouteHandler:
            if event_name in self._routes:
                raise ValueError(f"Handler already registered for {event_name.value}.")
            self._routes[event_name] = RouteDefinition(
                event_factory=lambda payload: build_event_model(payload, event_model),
                handler=handler,
                injected_arguments=build_injected_arguments(handler, event_model),
            )
            return handler

        return decorator


__all__ = ["AgentHook"]
