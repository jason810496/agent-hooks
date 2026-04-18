"""Block a Codex stop event until a test-like command has been observed."""

from __future__ import annotations

from pathlib import Path

from example_utils import (
    command_looks_test_like,
    compact_text,
    normalize_session_id,
    read_json_object,
    resolve_state_directory,
    write_json_object,
)

from agent_hooks import (
    AgentHook,
    HookProvider,
    HookResponse,
    PostToolUseEvent,
    StopEvent,
)
from agent_hooks.enums import HookControlDecision

DEFAULT_STATE_DIRECTORY = ".agent-hooks/test-before-stop"
STATE_DIRECTORY_ENV_VAR = "AGENT_HOOK_TEST_BEFORE_STOP_DIR"

app = AgentHook(fallback_to_default_processor=False, provider=HookProvider.CODEX)


def resolve_state_path(session_id: str, cwd: str) -> Path:
    """Resolve the persistent state file for one session.

    :param session_id: Session identifier from the hook payload.
    :type session_id: str
    :param cwd: Working directory from the hook payload.
    :type cwd: str
    :return: JSON state file path for the session.
    """
    state_directory = resolve_state_directory(
        cwd,
        env_var=STATE_DIRECTORY_ENV_VAR,
        default_subdir=DEFAULT_STATE_DIRECTORY,
    )
    return state_directory / f"{normalize_session_id(session_id)}.json"


def load_state(session_id: str, cwd: str) -> dict[str, object]:
    """Load the persistent test-tracking state for a session.

    :param session_id: Session identifier from the hook payload.
    :type session_id: str
    :param cwd: Working directory from the hook payload.
    :type cwd: str
    :return: Mutable state dictionary for the session.
    """
    return read_json_object(resolve_state_path(session_id, cwd))


def save_state(session_id: str, cwd: str, state: dict[str, object]) -> None:
    """Persist the test-tracking state for a session.

    :param session_id: Session identifier from the hook payload.
    :type session_id: str
    :param cwd: Working directory from the hook payload.
    :type cwd: str
    :param state: Mutable state dictionary to persist.
    :type state: dict[str, object]
    """
    write_json_object(resolve_state_path(session_id, cwd), state)


@app.post_tool_use()
def post_tool_use_handler(hook_event: PostToolUseEvent) -> HookResponse:
    """Record test-like commands observed during a session.

    :param hook_event: Post-tool-use event from Codex.
    :type hook_event: PostToolUseEvent
    :return: Empty hook response.
    """
    command = hook_event.tool_input.command.strip()
    if not command:
        return HookResponse()

    state = load_state(hook_event.session_id, hook_event.cwd)
    state["last_command"] = compact_text(command, limit=400)
    if command_looks_test_like(command):
        state["saw_test"] = True
        state["last_test_command"] = compact_text(command, limit=400)
    save_state(hook_event.session_id, hook_event.cwd, state)
    return HookResponse()


@app.stop()
def stop_handler(hook_event: StopEvent) -> HookResponse:
    """Block session completion when no test-like command was recorded.

    :param hook_event: Stop event from Codex.
    :type hook_event: StopEvent
    :return: Empty response when tests ran, otherwise a block response.
    """
    state = load_state(hook_event.session_id, hook_event.cwd)
    if state.get("saw_test") is True:
        return HookResponse()

    last_command = str(state.get("last_command", "")).strip()
    reason = "No test-like command was recorded for this session."
    if last_command:
        reason = f"{reason} Last recorded command: {last_command}"

    return HookResponse(
        decision=HookControlDecision.BLOCK,
        reason=reason,
        system_message="Run a targeted test command before ending the Codex session.",
    )
