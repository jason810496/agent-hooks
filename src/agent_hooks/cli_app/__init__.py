"""Expose the built-in CLI application."""

from __future__ import annotations

from agent_hooks.cli_app.app import app
from agent_hooks.cli_app.cli import main

__all__ = ["app", "main"]
