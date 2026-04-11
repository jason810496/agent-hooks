"""Provide the decorator-based router for agent hook callbacks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from inspect import Parameter, signature
from typing import IO, TypeAlias, TypeVar, get_type_hints

from agent_hooks.config import RuntimeConfig
from agent_hooks.enums import HookEventName
from agent_hooks.models import (
    HookInput,
    HookPayload,
    HookProcessingResult,
    HookResponse,
    HookResponseProtocol,
)
from agent_hooks.processor import process_hook
from agent_hooks.transport import DisplayTransport

EventModelT = TypeVar("EventModelT", bound=HookPayload)
HandlerResult: TypeAlias = HookProcessingResult | HookResponseProtocol | None
RouteHandler: TypeAlias = Callable[..., HandlerResult]
RouteDecorator: TypeAlias = Callable[[RouteHandler], RouteHandler]


@dataclass(frozen=True)
class NotificationEvent(HookPayload):
    """Represent a normalized notification hook payload."""


@dataclass(frozen=True)
class PermissionRequestEvent(HookPayload):
    """Represent a normalized permission request hook payload."""


@dataclass(frozen=True)
class StopEvent(HookPayload):
    """Represent a normalized stop hook payload."""


@dataclass(frozen=True)
class StopFailureEvent(HookPayload):
    """Represent a normalized failed-stop hook payload."""


@dataclass(frozen=True)
class CallbackRequest:
    """Expose the parsed callback request to routed handlers."""

    input_data: HookInput

    @property
    def raw_input(self) -> str:
        """Return the raw callback payload.

        :return: Raw UTF-8 callback body.
        """
        return self.input_data.raw_input

    @property
    def payload(self) -> HookPayload:
        """Return the normalized callback payload.

        :return: Parsed hook payload.
        """
        return self.input_data.payload

    @property
    def parse_error(self) -> str | None:
        """Return the callback parse error, when one exists.

        :return: Parse error message, or ``None``.
        """
        return self.input_data.parse_error

    def empty_response(self) -> HookResponse:
        """Build the default no-op hook response.

        :return: Default response payload.
        """
        return HookResponse()


@dataclass(frozen=True)
class _RouteDefinition:
    """Store one registered callback route."""

    event_factory: Callable[[HookPayload], HookPayload]
    handler: RouteHandler
    injected_arguments: tuple[_InjectedArgument, ...]


@dataclass(frozen=True)
class _InjectedArgument:
    """Store one handler parameter that should receive an injected value."""

    parameter_name: str
    value_kind: str


class AgentHook:
    """Register decorator-based callback handlers and dispatch hook events."""

    def __init__(self, *, fallback_to_default_processor: bool = True) -> None:
        """Initialize the hook router.

        :param fallback_to_default_processor: Whether to keep the built-in processor as a fallback.
        :type fallback_to_default_processor: bool
        """
        self._fallback_to_default_processor = fallback_to_default_processor
        self._routes: dict[HookEventName, _RouteDefinition] = {}

    def notification(self) -> RouteDecorator[NotificationEvent]:
        """Register a handler for ``Notification`` events.

        :return: Decorator that stores the handler.
        """
        return self._register(HookEventName.NOTIFICATION, NotificationEvent)

    def permission(self) -> RouteDecorator[PermissionRequestEvent]:
        """Register a handler for ``PermissionRequest`` events.

        :return: Decorator that stores the handler.
        """
        return self._register(HookEventName.PERMISSION_REQUEST, PermissionRequestEvent)

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
        :param transport: Display transport used by the fallback processor.
        :type transport: DisplayTransport
        :return: Processing result used by logging and output emission.
        """
        if input_data.parse_error is not None:
            return _empty_processing_result(error=input_data.parse_error)

        route = self._routes.get(input_data.payload.event_name)
        if route is None:
            if self._fallback_to_default_processor:
                return process_hook(input_data, transport)
            return _empty_processing_result()

        request = CallbackRequest(input_data=input_data)
        hook_event = route.event_factory(input_data.payload)
        result = _call_route_handler(route, request, hook_event, transport)
        return _coerce_route_result(result)

    def run_callback(
        self,
        *,
        stdin: IO[str] | None = None,
        stdout: IO[str] | None = None,
        runtime_config: RuntimeConfig | None = None,
        transport: DisplayTransport | None = None,
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
        :return: Process exit code.
        """
        from agent_hooks.runner import run_callback

        return run_callback(
            stdin=stdin,
            stdout=stdout,
            runtime_config=runtime_config,
            transport=transport,
            hook=self,
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
            self._routes[event_name] = _RouteDefinition(
                event_factory=lambda payload: _build_event_model(payload, event_model),
                handler=handler,
                injected_arguments=_build_injected_arguments(handler, event_model),
            )
            return handler

        return decorator


def _coerce_route_result(result: HandlerResult) -> HookProcessingResult:
    """Normalize a route handler result into a processing result.

    :param result: Raw handler return value.
    :type result: HandlerResult
    :return: Normalized processing result.
    """
    if isinstance(result, HookProcessingResult):
        return result

    return HookProcessingResult(
        display=None,
        transport_result=None,
        response=result if result is not None else HookResponse(),
    )


def _build_event_model(payload: HookPayload, event_model: type[EventModelT]) -> EventModelT:
    """Clone a base payload into a typed event model.

    :param payload: Parsed base payload.
    :type payload: HookPayload
    :param event_model: Event model subclass to instantiate.
    :type event_model: type[EventModelT]
    :return: Typed event model instance.
    """
    payload_values = {field.name: getattr(payload, field.name) for field in fields(HookPayload)}
    return event_model(**payload_values)


def _empty_processing_result(*, error: str | None = None) -> HookProcessingResult:
    """Build the default processing result without transport activity.

    :param error: Optional error message to preserve.
    :type error: str | None
    :return: Empty processing result.
    """
    return HookProcessingResult(
        display=None,
        transport_result=None,
        response=HookResponse(),
        error=error,
    )


def _call_route_handler(
    route: _RouteDefinition,
    request: CallbackRequest,
    hook_event: HookPayload,
    transport: DisplayTransport,
) -> HandlerResult:
    """Invoke a route handler with annotation-based parameter injection.

    :param route: Registered route definition.
    :type route: _RouteDefinition
    :param request: Callback request wrapper.
    :type request: CallbackRequest
    :param hook_event: Typed event model for this route.
    :type hook_event: HookPayload
    :param transport: Display transport used by the route handler.
    :type transport: DisplayTransport
    :return: Route handler response, or ``None``.
    """
    keyword_arguments = {
        argument.parameter_name: _resolve_injected_value(argument, request, hook_event, transport)
        for argument in route.injected_arguments
    }
    return route.handler(**keyword_arguments)


def _resolve_injected_value(
    argument: _InjectedArgument,
    request: CallbackRequest,
    hook_event: HookPayload,
    transport: DisplayTransport,
) -> object:
    """Resolve one injected argument value for a route handler.

    :param argument: Injected argument definition.
    :type argument: _InjectedArgument
    :param request: Callback request wrapper.
    :type request: CallbackRequest
    :param hook_event: Typed event model.
    :type hook_event: HookPayload
    :param transport: Display transport used by the route handler.
    :type transport: DisplayTransport
    :return: Injected value for the handler parameter.
    """
    if argument.value_kind == "request":
        return request
    if argument.value_kind == "transport":
        return transport
    return hook_event


def _build_injected_arguments(
    handler: RouteHandler,
    event_model: type[HookPayload],
) -> tuple[_InjectedArgument, ...]:
    """Build the injection plan for one route handler.

    :param handler: Handler registered for the route.
    :type handler: RouteHandler
    :param event_model: Event model allowed for this route.
    :type event_model: type[HookPayload]
    :return: Injected argument definitions in declaration order.
    :raises ValueError: If the handler has an unsupported required parameter.
    """
    resolved_annotations = get_type_hints(handler)
    injected_arguments: list[_InjectedArgument] = []
    for parameter in signature(handler).parameters.values():
        injected_argument = _build_injected_argument(
            handler,
            parameter,
            resolved_annotations.get(parameter.name, parameter.annotation),
            event_model,
        )
        if injected_argument is not None:
            injected_arguments.append(injected_argument)
            continue
        if parameter.kind in {Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD}:
            continue
        if parameter.default is not Parameter.empty:
            continue
        raise ValueError(_unsupported_parameter_message(handler, parameter, event_model))
    return tuple(injected_arguments)


def _build_injected_argument(
    handler: RouteHandler,
    parameter: Parameter,
    annotation: object,
    event_model: type[HookPayload],
) -> _InjectedArgument | None:
    """Return the injected argument definition for one handler parameter.

    :param handler: Handler registered for the route.
    :type handler: RouteHandler
    :param parameter: Handler parameter to inspect.
    :type parameter: Parameter
    :param annotation: Resolved parameter annotation.
    :type annotation: object
    :param event_model: Event model allowed for this route.
    :type event_model: type[HookPayload]
    :return: Injected argument definition, or ``None`` when unsupported.
    :raises ValueError: If an injectable parameter is positional-only.
    """
    value_kind = ""
    if annotation is CallbackRequest:
        value_kind = "request"
    elif annotation is DisplayTransport:
        value_kind = "transport"
    elif annotation is event_model:
        value_kind = "event"
    else:
        return None

    if parameter.kind == Parameter.POSITIONAL_ONLY:
        raise ValueError(
            f"Handler '{_handler_name(handler)}' cannot use positional-only injectable "
            f"parameter '{parameter.name}'."
        )

    return _InjectedArgument(parameter_name=parameter.name, value_kind=value_kind)


def _unsupported_parameter_message(
    handler: RouteHandler,
    parameter: Parameter,
    event_model: type[HookPayload],
) -> str:
    """Build the validation error for an unsupported required parameter.

    :param handler: Handler registered for the route.
    :type handler: RouteHandler
    :param parameter: Required parameter that cannot be injected.
    :type parameter: Parameter
    :param event_model: Event model allowed for this route.
    :type event_model: type[HookPayload]
    :return: User-facing validation message.
    """
    return (
        f"Handler '{_handler_name(handler)}' has unsupported required parameter "
        f"'{parameter.name}'. Annotate injectable parameters with CallbackRequest, "
        f"DisplayTransport, or {event_model.__name__}, or provide a default value."
    )


def _handler_name(handler: RouteHandler) -> str:
    """Return a readable name for a route handler.

    :param handler: Handler callable.
    :type handler: RouteHandler
    :return: Best-effort handler name.
    """
    return getattr(handler, "__name__", handler.__class__.__name__)
