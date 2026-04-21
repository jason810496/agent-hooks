"""Define permission-decision models shared by providers."""

from __future__ import annotations

from dataclasses import dataclass

from agent_hooks.enums import PermissionBehavior, PermissionDestination
from agent_hooks.models.schemas.json_types import JsonObject


@dataclass(frozen=True)
class PermissionUpdate:
    """Store one outgoing permission update for Claude."""

    source: JsonObject
    destination: PermissionDestination = PermissionDestination.SESSION

    def as_payload(self) -> JsonObject:
        """Serialize the permission update for Claude.

        :return: JSON payload with destination override applied.
        """
        return {**self.source, "destination": self.destination.value}


@dataclass(frozen=True)
class PermissionDecision:
    """Store the structured permission decision sent back to a provider."""

    behavior: PermissionBehavior
    updated_permissions: tuple[PermissionUpdate, ...] = ()

    def as_payload(self) -> JsonObject:
        """Serialize the permission decision.

        :return: JSON payload for Claude's hook protocol.
        """
        payload: JsonObject = {"behavior": self.behavior.value}
        if self.updated_permissions:
            payload["updatedPermissions"] = [
                update.as_payload() for update in self.updated_permissions
            ]
        return payload


__all__ = ["PermissionDecision", "PermissionUpdate"]
