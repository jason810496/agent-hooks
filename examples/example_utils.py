"""Shared helpers used by the example hook apps."""

from __future__ import annotations

import json
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path

SENSITIVE_FILE_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".npmrc",
        ".pypirc",
        "credentials",
        "id_ed25519",
        "id_rsa",
        "known_hosts",
    }
)
SENSITIVE_PATH_PARTS = frozenset({".aws", ".gnupg", ".ssh", ".terraform"})
SENSITIVE_SUFFIXES = frozenset({".asc", ".key", ".pem", ".p12", ".pfx"})
TEST_COMMAND_MARKERS = (
    "cargo test",
    "go test",
    "npm test",
    "pnpm test",
    "pytest",
    "uv run pytest",
    "yarn test",
    "./gradlew test",
)


def now_timestamp() -> str:
    """Return the current UTC timestamp.

    :return: ISO 8601 UTC timestamp.
    """
    return datetime.now(timezone.utc).isoformat()


def compact_text(text: str, *, limit: int = 240) -> str:
    """Compact multi-line text into one bounded line.

    :param text: Raw text value to compact.
    :type text: str
    :param limit: Maximum output length.
    :type limit: int
    :return: One-line compacted text preview.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."


def normalize_session_id(session_id: str) -> str:
    """Return a filesystem-safe session identifier.

    :param session_id: Raw session identifier from the hook payload.
    :type session_id: str
    :return: Sanitized identifier suitable for a filename.
    """
    cleaned = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in session_id
    )
    return cleaned or "unknown-session"


def resolve_state_directory(cwd: str, *, env_var: str, default_subdir: str) -> Path:
    """Resolve a state directory relative to the callback working directory.

    :param cwd: Working directory from the hook payload.
    :type cwd: str
    :param env_var: Environment variable that overrides the default directory.
    :type env_var: str
    :param default_subdir: Default directory relative to ``cwd``.
    :type default_subdir: str
    :return: Resolved state directory path.
    """
    configured_directory = os.environ.get(env_var, "").strip()
    base_directory = Path(cwd) if cwd else Path.cwd()
    if configured_directory:
        state_directory = Path(configured_directory).expanduser()
        if not state_directory.is_absolute():
            state_directory = base_directory / state_directory
        return state_directory
    return base_directory / default_subdir


def append_jsonl(path: Path, record: dict[str, object]) -> None:
    """Append one JSON record to a JSONL file.

    :param path: Target JSONL file path.
    :type path: pathlib.Path
    :param record: JSON-serializable record to append.
    :type record: dict[str, object]
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(record, handle, separators=(",", ":"))
        handle.write("\n")


def read_json_object(path: Path) -> dict[str, object]:
    """Read a JSON object from disk when it exists.

    :param path: JSON file path.
    :type path: pathlib.Path
    :return: Parsed object, or an empty dictionary when unavailable.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}

    if isinstance(parsed, dict):
        return dict(parsed)
    return {}


def write_json_object(path: Path, payload: dict[str, object]) -> None:
    """Write one JSON object to disk.

    :param path: Target JSON file path.
    :type path: pathlib.Path
    :param payload: JSON-serializable object to store.
    :type payload: dict[str, object]
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def tokenize_command(command: str) -> list[str]:
    """Tokenize a shell command conservatively.

    :param command: Raw shell command from the hook payload.
    :type command: str
    :return: Tokenized arguments, or an empty list on parse failure.
    """
    try:
        return shlex.split(command)
    except ValueError:
        return []


def text_looks_like_path(token: str) -> bool:
    """Return whether a token resembles a filesystem path.

    :param token: One shell token from a command string.
    :type token: str
    :return: ``True`` when the token looks path-like.
    """
    if not token or token in {"|", "&&", "||", ";"}:
        return False
    candidate = token
    if candidate.startswith("@"):
        candidate = candidate[1:]
    if "=" in candidate and candidate.split("=", 1)[0].startswith("-"):
        candidate = candidate.split("=", 1)[1]
    if candidate.startswith("@"):
        candidate = candidate[1:]

    if candidate.startswith(("http://", "https://", "s3://", "gs://")):
        return False
    if candidate.startswith("-") and candidate not in {".", ".."}:
        return False
    if "/" in candidate or candidate.startswith((".", "~")):
        return True

    lower_token = candidate.lower()
    if lower_token in SENSITIVE_FILE_NAMES:
        return True
    return Path(candidate).suffix.lower() in SENSITIVE_SUFFIXES


def command_path_tokens(command: str) -> tuple[str, ...]:
    """Return path-like tokens referenced by a shell command.

    :param command: Raw shell command from the hook payload.
    :type command: str
    :return: Tuple of candidate path tokens.
    """
    collected_paths: list[str] = []
    for token in tokenize_command(command)[1:]:
        if not text_looks_like_path(token):
            continue

        candidate = token
        if candidate.startswith("@"):
            candidate = candidate[1:]
        if "=" in candidate and candidate.split("=", 1)[0].startswith("-"):
            candidate = candidate.split("=", 1)[1]
        if candidate.startswith("@"):
            candidate = candidate[1:]
        collected_paths.append(candidate)
    return tuple(collected_paths)


def resolve_path_token(raw_path: str, cwd: str) -> Path | None:
    """Resolve one raw path token relative to the callback working directory.

    :param raw_path: Raw path token from a hook payload.
    :type raw_path: str
    :param cwd: Working directory from the hook payload.
    :type cwd: str
    :return: Resolved path, or ``None`` for tokens that are not local paths.
    """
    if not raw_path or raw_path.startswith(("http://", "https://", "s3://", "gs://")):
        return None
    if ":" in raw_path and not raw_path.startswith(("/", "./", "../", "~")):
        return None

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        base_directory = Path(cwd) if cwd else Path.cwd()
        path = base_directory / path
    return path.resolve(strict=False)


def path_is_within_root(path: Path, root: Path) -> bool:
    """Return whether a path stays inside a root directory.

    :param path: Path to check.
    :type path: pathlib.Path
    :param root: Root directory that bounds the path.
    :type root: pathlib.Path
    :return: ``True`` when the path is inside the root.
    """
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def path_is_sensitive(path: Path) -> bool:
    """Return whether a path looks like sensitive credential material.

    :param path: Path to inspect.
    :type path: pathlib.Path
    :return: ``True`` when the path should be treated as sensitive.
    """
    lower_parts = {part.lower() for part in path.parts}
    if lower_parts & SENSITIVE_PATH_PARTS:
        return True

    lower_name = path.name.lower()
    if lower_name in SENSITIVE_FILE_NAMES:
        return True
    return path.suffix.lower() in SENSITIVE_SUFFIXES


def command_mentions_sensitive_path(command: str, cwd: str) -> bool:
    """Return whether a shell command references a sensitive local path.

    :param command: Raw shell command from the hook payload.
    :type command: str
    :param cwd: Working directory from the hook payload.
    :type cwd: str
    :return: ``True`` when any local path in the command looks sensitive.
    """
    for raw_path in command_path_tokens(command):
        resolved_path = resolve_path_token(raw_path, cwd)
        if resolved_path is not None and path_is_sensitive(resolved_path):
            return True
    return False


def command_looks_test_like(command: str) -> bool:
    """Return whether a shell command looks like a test invocation.

    :param command: Raw shell command from the hook payload.
    :type command: str
    :return: ``True`` when the command resembles a test run.
    """
    normalized_command = command.lower()
    return any(marker in normalized_command for marker in TEST_COMMAND_MARKERS)
