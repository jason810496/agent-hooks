"""Dependency marker objects for router parameter injection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Depends:
    """Declare one route dependency to resolve before calling the handler.

    Dependencies may return a plain value, a context manager, or a generator that
    yields exactly one value and then performs cleanup.

    :param dependency: Callable dependency to execute for the parameter value.
    :type dependency: Callable[..., object]
    :raises TypeError: If ``dependency`` is not callable.
    """

    dependency: Callable[..., object]

    def __post_init__(self) -> None:
        """Validate the dependency callable.

        :raises TypeError: If ``dependency`` is not callable.
        """
        if not callable(self.dependency):
            raise TypeError("Depends() requires a callable dependency.")


__all__ = ["Depends"]
