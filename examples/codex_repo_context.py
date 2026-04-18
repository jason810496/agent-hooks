"""Inject compact repository context into Codex session start."""

from __future__ import annotations

from pathlib import Path

from agent_hooks import AgentHook, HookProvider, HookResponse, SessionStartEvent
from agent_hooks.enums import HookEventName
from agent_hooks.models import HookSpecificOutput

CANDIDATE_FILES = (
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "package.json",
    "Makefile",
)
MAX_CONTEXT_LENGTH = 1800

app = AgentHook(fallback_to_default_processor=False, provider=HookProvider.CODEX)


def preview_file(path: Path, *, max_lines: int = 8, max_characters: int = 400) -> str:
    """Return a compact preview of a local text file.

    :param path: File to preview.
    :type path: pathlib.Path
    :param max_lines: Maximum number of non-empty lines to keep.
    :type max_lines: int
    :param max_characters: Maximum length of the returned preview.
    :type max_characters: int
    :return: One-line preview string.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    non_empty_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    preview = " | ".join(non_empty_lines[:max_lines])
    if len(preview) <= max_characters:
        return preview
    return f"{preview[: max_characters - 3]}..."


def build_additional_context(cwd: str) -> str:
    """Build repository context from a few common project files.

    :param cwd: Working directory from the session-start event.
    :type cwd: str
    :return: Additional context string for Codex, or an empty string.
    """
    project_root = Path(cwd) if cwd else Path.cwd()
    context_lines = [
        "Local repository context gathered by Agent Hooks.",
        f"Project root: {project_root}",
    ]

    found_files = 0
    for relative_path in CANDIDATE_FILES:
        candidate = project_root / relative_path
        if not candidate.is_file():
            continue

        preview = preview_file(candidate)
        if not preview:
            continue

        context_lines.append(f"{relative_path}: {preview}")
        found_files += 1

    if found_files == 0:
        return ""

    context_lines.append(
        "Prefer repository-specific instructions from AGENTS.md and README.md when they exist."
    )
    additional_context = "\n".join(context_lines)
    if len(additional_context) <= MAX_CONTEXT_LENGTH:
        return additional_context
    return f"{additional_context[: MAX_CONTEXT_LENGTH - 3]}..."


@app.session_start()
def session_start_handler(hook_event: SessionStartEvent) -> HookResponse:
    """Attach repository context to a Codex session-start event.

    :param hook_event: Session-start event from Codex.
    :type hook_event: SessionStartEvent
    :return: Response with optional additional context.
    """
    additional_context = build_additional_context(hook_event.cwd)
    if not additional_context:
        return HookResponse()

    return HookResponse(
        hook_specific_output=HookSpecificOutput(
            hook_event_name=HookEventName.SESSION_START,
            additional_context=additional_context,
        )
    )
