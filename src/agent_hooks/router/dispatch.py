"""Internal helpers for route dispatch and parameter injection."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import ExitStack
from dataclasses import fields
from inspect import Parameter, isgenerator, signature
from typing import get_type_hints

from agent_hooks.models.events import HookEvent
from agent_hooks.models.schemas.hooks import HookPayload
from agent_hooks.models.schemas.processing import HookProcessingResult
from agent_hooks.models.schemas.responses import HookResponse
from agent_hooks.router.definitions import (
    DependencyCallable,
    DependencyDefinition,
    EventModelT,
    HandlerResult,
    InjectedArgument,
    RouteDefinition,
    RouteHandler,
)
from agent_hooks.router.dependencies import Depends
from agent_hooks.router.request import CallbackRequest
from agent_hooks.transport import DisplayTransport

_MISSING_DEPENDENCY_VALUE = object()


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
    """Invoke a route handler with router-managed parameter injection.

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
    dependency_cache: dict[DependencyCallable, object] = {}
    with ExitStack() as exit_stack:
        keyword_arguments = {
            argument.parameter_name: _resolve_injected_value(
                argument,
                request,
                hook_event,
                transport,
                dependency_cache,
                exit_stack,
            )
            for argument in route.injected_arguments
        }
        return route.handler(**keyword_arguments)


def _resolve_injected_value(
    argument: InjectedArgument,
    request: CallbackRequest,
    hook_event: HookEvent,
    transport: DisplayTransport,
    dependency_cache: dict[DependencyCallable, object],
    exit_stack: ExitStack,
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
    :param dependency_cache: Per-dispatch dependency value cache.
    :type dependency_cache: dict[DependencyCallable, object]
    :param exit_stack: Per-dispatch lifecycle stack for dependency cleanup.
    :type exit_stack: ExitStack
    :return: Injected value for the handler parameter.
    """
    if argument.value_kind == "request":
        return request
    if argument.value_kind == "transport":
        return transport
    if argument.value_kind == "dependency":
        return _resolve_dependency(
            argument,
            request,
            hook_event,
            transport,
            dependency_cache,
            exit_stack,
        )
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
    return _build_callable_injected_arguments(
        handler,
        event_model,
        owner_kind="Handler",
        allow_depends=True,
    )


def _resolve_callable_annotations(
    handler: RouteHandler | DependencyCallable,
) -> dict[str, object]:
    """Return resolved type hints from the callable that ``signature()`` inspects.

    ``signature()`` reports ``__init__`` parameters for a class and ``__call__``
    parameters for a callable instance, so the annotations must be resolved from the
    same target. Resolving ``get_type_hints(handler)`` directly would read class
    attribute annotations instead, leaving parameter annotations as unparsed strings
    under ``from __future__ import annotations``.

    :param handler: Function, method, class, or callable instance to inspect.
    :type handler: RouteHandler | DependencyCallable
    :return: Mapping of parameter name to resolved type hint.
    """
    if isinstance(handler, type):
        if handler.__init__ is object.__init__:
            # A class without its own ``__init__`` exposes ``object``'s slot wrapper,
            # which ``get_type_hints`` cannot inspect on some Python versions.
            return {}
        return get_type_hints(handler.__init__)
    if not hasattr(handler, "__code__"):
        # Callable instances expose parameters through their class ``__call__`` rather
        # than ``__code__`` (which functions, methods, and lambdas carry directly).
        return get_type_hints(type(handler).__call__)
    return get_type_hints(handler)


def _build_callable_injected_arguments(
    handler: RouteHandler | DependencyCallable,
    event_model: type[HookEvent],
    *,
    owner_kind: str,
    allow_depends: bool,
) -> tuple[InjectedArgument, ...]:
    """Build the injection plan for one callable.

    :param handler: Callable whose parameters should be inspected.
    :type handler: RouteHandler | DependencyCallable
    :param event_model: Event model allowed for this route.
    :type event_model: type[HookEvent]
    :param owner_kind: Human-readable callable category used in errors.
    :type owner_kind: str
    :param allow_depends: Whether ``Depends(...)`` is supported for this callable.
    :type allow_depends: bool
    :return: Injected argument definitions in declaration order.
    :raises ValueError: If the callable has an unsupported required parameter.
    """
    resolved_annotations = _resolve_callable_annotations(handler)
    injected_arguments: list[InjectedArgument] = []
    for parameter in signature(handler).parameters.values():
        dependency_argument = _build_dependency_argument(
            handler,
            parameter,
            event_model,
            owner_kind=owner_kind,
            allow_depends=allow_depends,
        )
        if dependency_argument is not None:
            injected_arguments.append(dependency_argument)
            continue
        injected_argument = _build_injected_argument(
            handler,
            parameter,
            resolved_annotations.get(parameter.name, parameter.annotation),
            event_model,
            owner_kind=owner_kind,
        )
        if injected_argument is not None:
            injected_arguments.append(injected_argument)
            continue
        if parameter.kind in {Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD}:
            continue
        if parameter.default is not Parameter.empty:
            continue
        raise ValueError(
            _unsupported_parameter_message(
                handler,
                parameter,
                event_model,
                owner_kind=owner_kind,
                allow_depends=allow_depends,
            )
        )
    return tuple(injected_arguments)


def _build_injected_argument(
    handler: RouteHandler | DependencyCallable,
    parameter: Parameter,
    annotation: object,
    event_model: type[HookEvent],
    *,
    owner_kind: str,
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
            f"{owner_kind} '{_handler_name(handler)}' cannot use positional-only injectable "
            f"parameter '{parameter.name}'."
        )

    return InjectedArgument(parameter_name=parameter.name, value_kind=value_kind)


def _build_dependency_argument(
    handler: RouteHandler | DependencyCallable,
    parameter: Parameter,
    event_model: type[HookEvent],
    *,
    owner_kind: str,
    allow_depends: bool,
) -> InjectedArgument | None:
    """Build the dependency injection definition for one parameter.

    :param handler: Callable that owns the parameter.
    :type handler: RouteHandler | DependencyCallable
    :param parameter: Callable parameter to inspect.
    :type parameter: Parameter
    :param event_model: Event model allowed for this route.
    :type event_model: type[HookEvent]
    :param owner_kind: Human-readable callable category used in errors.
    :type owner_kind: str
    :param allow_depends: Whether ``Depends(...)`` is supported for this callable.
    :type allow_depends: bool
    :return: Dependency-backed injected argument, or ``None``.
    :raises ValueError: If nested dependencies are declared.
    """
    if not isinstance(parameter.default, Depends):
        return None

    if parameter.kind == Parameter.POSITIONAL_ONLY:
        raise ValueError(
            f"{owner_kind} '{_handler_name(handler)}' cannot use positional-only "
            f"dependency parameter '{parameter.name}'."
        )

    if not allow_depends:
        raise ValueError(
            f"{owner_kind} '{_handler_name(handler)}' cannot use nested Depends for "
            f"parameter '{parameter.name}'. Only one dependency level is supported."
        )

    dependency = _build_dependency_definition(parameter.default.dependency, event_model)
    return InjectedArgument(
        parameter_name=parameter.name,
        value_kind="dependency",
        dependency=dependency,
    )


def _build_dependency_definition(
    dependency: DependencyCallable,
    event_model: type[HookEvent],
) -> DependencyDefinition:
    """Build the injection plan for one dependency callable.

    :param dependency: Dependency callable to inspect.
    :type dependency: DependencyCallable
    :param event_model: Event model allowed for this route.
    :type event_model: type[HookEvent]
    :return: Dependency definition with its injection plan.
    """
    return DependencyDefinition(
        dependency=dependency,
        injected_arguments=_build_callable_injected_arguments(
            dependency,
            event_model,
            owner_kind="Dependency",
            allow_depends=False,
        ),
    )


def _resolve_dependency(
    argument: InjectedArgument,
    request: CallbackRequest,
    hook_event: HookEvent,
    transport: DisplayTransport,
    dependency_cache: dict[DependencyCallable, object],
    exit_stack: ExitStack,
) -> object:
    """Resolve one dependency-backed injected value.

    :param argument: Dependency-backed injected argument definition.
    :type argument: InjectedArgument
    :param request: Callback request wrapper.
    :type request: CallbackRequest
    :param hook_event: Typed event model.
    :type hook_event: HookEvent
    :param transport: Display transport used by the route handler.
    :type transport: DisplayTransport
    :param dependency_cache: Per-dispatch dependency value cache.
    :type dependency_cache: dict[DependencyCallable, object]
    :param exit_stack: Per-dispatch lifecycle stack for dependency cleanup.
    :type exit_stack: ExitStack
    :return: Dependency return value.
    :raises ValueError: If the dependency definition is unexpectedly missing.
    """
    dependency = argument.dependency
    if dependency is None:
        raise ValueError(
            f"Injected dependency parameter '{argument.parameter_name}' is missing a "
            "dependency definition."
        )

    cached_value = dependency_cache.get(dependency.dependency, _MISSING_DEPENDENCY_VALUE)
    if cached_value is not _MISSING_DEPENDENCY_VALUE:
        return cached_value

    keyword_arguments = {
        nested_argument.parameter_name: _resolve_injected_value(
            nested_argument,
            request,
            hook_event,
            transport,
            dependency_cache,
            exit_stack,
        )
        for nested_argument in dependency.injected_arguments
    }
    result = _coerce_dependency_result(
        dependency.dependency,
        dependency.dependency(**keyword_arguments),
        exit_stack,
    )
    dependency_cache[dependency.dependency] = result
    return result


def _coerce_dependency_result(
    dependency: DependencyCallable,
    result: object,
    exit_stack: ExitStack,
) -> object:
    """Normalize one dependency result into an injected value.

    :param dependency: Dependency callable that produced ``result``.
    :type dependency: DependencyCallable
    :param result: Raw dependency return value.
    :type result: object
    :param exit_stack: Per-dispatch lifecycle stack for dependency cleanup.
    :type exit_stack: ExitStack
    :return: Injected dependency value.
    """
    if _is_context_manager(result):
        return exit_stack.enter_context(result)
    if isgenerator(result):
        return exit_stack.enter_context(
            _GeneratorDependencyScope(result, _handler_name(dependency))
        )
    return result


def _is_context_manager(value: object) -> bool:
    """Return whether one value behaves like a synchronous context manager.

    :param value: Value to inspect.
    :type value: object
    :return: ``True`` when the value implements ``__enter__`` and ``__exit__``.
    """
    enter = getattr(value, "__enter__", None)
    exit_ = getattr(value, "__exit__", None)
    return callable(enter) and callable(exit_)


class _GeneratorDependencyScope:
    """Drive a one-shot generator dependency as a context manager.

    Teardown mirrors :func:`contextlib.contextmanager` semantics so an exception raised
    by the route handler is thrown back into the dependency generator. This lets a
    dependency run ``except`` / ``finally`` cleanup correctly (for example rolling back
    on error), while still enforcing the single-yield contract.
    """

    def __init__(self, generator: Generator[object, None, None], dependency_name: str) -> None:
        """Store the generator and a readable dependency name.

        :param generator: Generator returned by a dependency callable.
        :type generator: Generator[object, None, None]
        :param dependency_name: Readable dependency name for error messages.
        :type dependency_name: str
        """
        self._generator = generator
        self._dependency_name = dependency_name

    def __enter__(self) -> object:
        """Advance the generator to its single yield and return the yielded value.

        :return: Value yielded by the dependency generator.
        :raises ValueError: If the generator yields no value.
        """
        try:
            return next(self._generator)
        except StopIteration as error:
            raise ValueError(self._single_yield_message()) from error

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        """Finalize the generator, propagating any handler exception into it.

        :param exc_type: Exception type raised by the handler, if any.
        :type exc_type: type[BaseException] | None
        :param exc_value: Exception instance raised by the handler, if any.
        :type exc_value: BaseException | None
        :param traceback: Active traceback, if any.
        :type traceback: object
        :return: Whether the handler exception was suppressed by the dependency.
        :raises ValueError: If the generator yields more than one value.
        """
        if exc_type is None:
            try:
                next(self._generator)
            except StopIteration:
                return False
            self._generator.close()
            raise ValueError(self._single_yield_message())

        if exc_value is None:
            exc_value = exc_type()
        try:
            self._generator.throw(exc_value)
        except StopIteration as stop:
            return stop is not exc_value
        except RuntimeError as runtime_error:
            if runtime_error is exc_value:
                return False
            if (
                isinstance(exc_value, StopIteration | StopAsyncIteration)
                and runtime_error.__cause__ is exc_value
            ):
                return False
            raise
        except BaseException as raised:
            if raised is not exc_value:
                raise
            return False
        raise ValueError(self._single_yield_message())

    def _single_yield_message(self) -> str:
        """Return the single-yield contract violation message.

        :return: User-facing validation message.
        """
        return f"Dependency '{self._dependency_name}' must yield exactly one value."


def _unsupported_parameter_message(
    handler: RouteHandler | DependencyCallable,
    parameter: Parameter,
    event_model: type[HookEvent],
    *,
    owner_kind: str,
    allow_depends: bool,
) -> str:
    """Build the validation error for an unsupported required parameter.

    :param handler: Handler registered for the route.
    :type handler: RouteHandler | DependencyCallable
    :param parameter: Required parameter that cannot be injected.
    :type parameter: Parameter
    :param event_model: Event model allowed for this route.
    :type event_model: type[HookEvent]
    :param owner_kind: Human-readable callable category used in errors.
    :type owner_kind: str
    :param allow_depends: Whether ``Depends(...)`` is supported for this callable.
    :type allow_depends: bool
    :return: User-facing validation message.
    """
    dependency_note = ""
    if allow_depends:
        dependency_note = ", declare a dependency with Depends(...),"
    return (
        f"{owner_kind} '{_handler_name(handler)}' has unsupported required parameter "
        f"'{parameter.name}'. Annotate injectable parameters with CallbackRequest, "
        f"DisplayTransport, or {event_model.__name__}{dependency_note} or provide a "
        "default value."
    )


def _handler_name(handler: RouteHandler | DependencyCallable) -> str:
    """Return a readable name for a callable.

    :param handler: Callable object.
    :type handler: RouteHandler | DependencyCallable
    :return: Best-effort callable name.
    """
    return getattr(handler, "__name__", handler.__class__.__name__)


__all__ = [
    "build_event_model",
    "build_injected_arguments",
    "call_route_handler",
    "coerce_route_result",
    "empty_processing_result",
]
