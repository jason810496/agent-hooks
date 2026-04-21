"""Internal helpers for route dispatch and parameter injection."""

from __future__ import annotations

from dataclasses import fields
from inspect import Parameter, signature
from typing import get_type_hints

from agent_hooks.models.events import HookEvent
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.processing import HookProcessingResult
from agent_hooks.models.schemas.responses import HookResponse
from agent_hooks.router.definitions import (
    EventModelT,
    HandlerResult,
    InjectedArgument,
    RouteDefinition,
    RouteHandler,
)
from agent_hooks.router.request import CallbackRequest
from agent_hooks.transport import DisplayTransport


def coerce_route_result(result: HandlerResult) -> HookProcessingResult:
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


def build_event_model(payload: HookPayload, event_model: type[EventModelT]) -> EventModelT:
    """Build one routed event model from the normalized payload.

    :param payload: Parsed base payload.
    :type payload: HookPayload
    :param event_model: Event model subclass to instantiate.
    :type event_model: type[EventModelT]
    :return: Typed event model instance.
    """
    payload_values = {field.name: getattr(payload, field.name) for field in fields(event_model)}
    return event_model(**payload_values)


def empty_processing_result(*, error: str | None = None) -> HookProcessingResult:
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


def call_route_handler(
    route: RouteDefinition,
    request: CallbackRequest,
    hook_event: HookEvent,
    transport: DisplayTransport,
) -> HandlerResult:
    """Invoke a route handler with annotation-based parameter injection.

    :param route: Registered route definition.
    :type route: RouteDefinition
    :param request: Callback request wrapper.
    :type request: CallbackRequest
    :param hook_event: Typed event model for this route.
    :type hook_event: HookEvent
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
    argument: InjectedArgument,
    request: CallbackRequest,
    hook_event: HookEvent,
    transport: DisplayTransport,
) -> object:
    """Resolve one injected argument value for a route handler.

    :param argument: Injected argument definition.
    :type argument: InjectedArgument
    :param request: Callback request wrapper.
    :type request: CallbackRequest
    :param hook_event: Typed event model.
    :type hook_event: HookEvent
    :param transport: Display transport used by the route handler.
    :type transport: DisplayTransport
    :return: Injected value for the handler parameter.
    """
    if argument.value_kind == "request":
        return request
    if argument.value_kind == "transport":
        return transport
    return hook_event


def build_injected_arguments(
    handler: RouteHandler,
    event_model: type[HookEvent],
) -> tuple[InjectedArgument, ...]:
    """Build the injection plan for one route handler.

    :param handler: Handler registered for the route.
    :type handler: RouteHandler
    :param event_model: Event model allowed for this route.
    :type event_model: type[HookEvent]
    :return: Injected argument definitions in declaration order.
    :raises ValueError: If the handler has an unsupported required parameter.
    """
    resolved_annotations = get_type_hints(handler)
    injected_arguments: list[InjectedArgument] = []
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
    event_model: type[HookEvent],
) -> InjectedArgument | None:
    """Return the injected argument definition for one handler parameter.

    :param handler: Handler registered for the route.
    :type handler: RouteHandler
    :param parameter: Handler parameter to inspect.
    :type parameter: Parameter
    :param annotation: Resolved parameter annotation.
    :type annotation: object
    :param event_model: Event model allowed for this route.
    :type event_model: type[HookEvent]
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

    return InjectedArgument(parameter_name=parameter.name, value_kind=value_kind)


def _unsupported_parameter_message(
    handler: RouteHandler,
    parameter: Parameter,
    event_model: type[HookEvent],
) -> str:
    """Build the validation error for an unsupported required parameter.

    :param handler: Handler registered for the route.
    :type handler: RouteHandler
    :param parameter: Required parameter that cannot be injected.
    :type parameter: Parameter
    :param event_model: Event model allowed for this route.
    :type event_model: type[HookEvent]
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


__all__ = [
    "build_event_model",
    "build_injected_arguments",
    "call_route_handler",
    "coerce_route_result",
    "empty_processing_result",
]
