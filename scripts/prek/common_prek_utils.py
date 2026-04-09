#!/usr/bin/env python3
"""Shared utilities for local prek validation hooks."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2].resolve()
SRC_PATH = PROJECT_ROOT / "src"


def print_error(message: str) -> None:
    """Write an error message to stderr.

    :param message: Error text to display.
    :type message: str
    :return: ``None``.
    """
    print(message, file=sys.stderr)


def print_success(message: str) -> None:
    """Write a success message to stderr.

    :param message: Success text to display.
    :type message: str
    :return: ``None``.
    """
    print(message, file=sys.stderr)


def parse_python_file(path: Path) -> ast.AST:
    """Parse a Python file into an AST.

    :param path: File to parse.
    :type path: Path
    :return: Parsed syntax tree.
    :raises SyntaxError: If the file contains invalid Python syntax.
    """
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
