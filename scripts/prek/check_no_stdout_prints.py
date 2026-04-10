#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Reject ``print()`` calls that could corrupt Agent hook stdout."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

from common_prek_utils import parse_python_file, print_error, print_success


def _targets_stderr(node: ast.expr) -> bool:
    """Return whether a ``print(file=...)`` target points at stderr.

    :param node: AST node used as the ``file`` keyword value.
    :type node: ast.expr
    :return: ``True`` when the target is ``sys.stderr`` or ``sys.__stderr__``.
    :rtype: bool
    """
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
        and node.attr in {"stderr", "__stderr__"}
    )


def check_file(path: Path) -> list[str]:
    """Return validation errors for stdout ``print()`` usage.

    :param path: Python source file to inspect.
    :type path: Path
    :return: Error messages for invalid ``print()`` calls.
    :rtype: list[str]
    """
    tree = parse_python_file(path)
    errors: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "print":
            continue

        file_keyword = next((kw for kw in node.keywords if kw.arg == "file"), None)
        if (
            file_keyword is not None
            and file_keyword.value is not None
            and _targets_stderr(file_keyword.value)
        ):
            continue

        errors.append(
            f"{path}:{node.lineno}: avoid print() in hook source; "
            "write to stderr or use logging so stdout stays valid JSON"
        )

    return errors


def main(argv: list[str] | None = None) -> int:
    """Validate files passed by prek.

    :param argv: Optional CLI argument override.
    :type argv: list[str] | None
    :return: Process exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)

    errors: list[str] = []
    for path in args.files:
        if path.suffix == ".py" and path.exists():
            errors.extend(check_file(path))

    if errors:
        for error in errors:
            print_error(error)
        return 1

    print_success("No stdout print() calls found in hook source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
