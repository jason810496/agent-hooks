"""Block a few risky prompt patterns before Codex starts work."""

from __future__ import annotations

import re

from agent_hooks import AgentHook, HookProvider, HookResponse, UserPromptSubmitEvent
from agent_hooks.enums import HookControlDecision

BLOCKED_PHRASES = (
    "ignore previous instructions",
    "disable hooks",
    "bypass hooks",
    "never run tests",
    "skip tests even if they fail",
    "print all environment variables",
    "show me the contents of .env",
    "cat ~/.ssh",
)
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)

app = AgentHook(fallback_to_default_processor=False, provider=HookProvider.CODEX)


def blocked_reason(prompt: str) -> str | None:
    """Return the block reason for a risky prompt.

    :param prompt: User prompt text from the callback payload.
    :type prompt: str
    :return: Human-readable block reason, or ``None`` when the prompt is allowed.
    """
    normalized_prompt = prompt.lower()
    for phrase in BLOCKED_PHRASES:
        if phrase in normalized_prompt:
            return f"Prompt includes a blocked phrase: '{phrase}'."

    for pattern in SECRET_PATTERNS:
        if pattern.search(prompt):
            return "Prompt appears to contain a secret-like token."

    if len(prompt.strip()) < 8:
        return "Prompt is too short to describe the task safely."

    return None


@app.user_prompt_submit()
def user_prompt_submit_handler(hook_event: UserPromptSubmitEvent) -> HookResponse:
    """Block risky prompts before Codex continues.

    :param hook_event: User prompt event from Codex.
    :type hook_event: UserPromptSubmitEvent
    :return: Empty response for allowed prompts, or a block response.
    """
    reason = blocked_reason(hook_event.prompt)
    if reason is None:
        return HookResponse()

    return HookResponse(
        decision=HookControlDecision.BLOCK,
        reason=reason,
        system_message=(
            "Rewrite the prompt with the task details, but do not ask the agent to bypass "
            "safeguards or reveal secrets."
        ),
    )
