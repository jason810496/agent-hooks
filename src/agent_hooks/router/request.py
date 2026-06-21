"""Request wrapper helpers for routed hook callbacks."""

from __future__ import annotations

from dataclasses import dataclass

from agent_hooks.models.schemas.hooks import HookInput, HookPayload
from agent_hooks.models.schemas.responses import HookResponse


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


__all__ = ["CallbackRequest"]
