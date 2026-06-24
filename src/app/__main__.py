"""Run the built-in CLI application as a package module."""

from __future__ import annotations

from app.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
