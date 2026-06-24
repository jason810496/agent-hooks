"""Resolve the queue key (repo / worktree root) a request belongs to."""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_TOPLEVEL_TIMEOUT_SECONDS = 2.0


def resolve_queue(cwd: str) -> str:
    """Return the queue key for one working directory.

    Each repo or worktree is its own queue. ``git rev-parse --show-toplevel``
    returns the worktree root (distinct per linked worktree), which is exactly the
    grouping we want. Falls back to the working directory when ``cwd`` is not a git
    checkout or git is unavailable.

    :param cwd: Working directory reported by the hook payload.
    :type cwd: str
    :return: Absolute repo/worktree root, or a sensible fallback path.
    """
    candidate = cwd.strip() if cwd else ""
    if candidate:
        try:
            result = subprocess.run(
                ["git", "-C", candidate, "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_TOPLEVEL_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0:
            toplevel = result.stdout.strip()
            if toplevel:
                return toplevel
        return candidate
    return str(Path.cwd())


__all__ = ["resolve_queue"]
