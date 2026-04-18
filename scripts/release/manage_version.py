#!/usr/bin/env python3
"""Inspect, validate, and update release versions for Agent Hooks."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.release.common import (
    PYPROJECT_PATH,
    ReleaseChannel,
    ReleaseManagementError,
    ensure_project_version_matches,
    ensure_version_matches_tag,
    extract_version_from_tag,
    read_project_version,
    validate_release_version,
    write_project_version,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    :return: Configured parser instance.
    """
    parser = argparse.ArgumentParser(
        description="Manage the static package version used for Agent Hooks releases."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser("show", help="Print the current project version.")
    show_parser.add_argument(
        "--pyproject",
        type=Path,
        default=PYPROJECT_PATH,
        help="Path to the pyproject.toml file to inspect.",
    )

    set_parser = subparsers.add_parser("set", help="Update pyproject.toml to a new version.")
    set_parser.add_argument("--version", required=True, help="New version like 0.2.0 or 0.2.0rc1.")
    set_parser.add_argument(
        "--pyproject",
        type=Path,
        default=PYPROJECT_PATH,
        help="Path to the pyproject.toml file to update.",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a version string, tag, and optional pyproject.toml match.",
    )
    validate_parser.add_argument(
        "--version",
        help="Explicit version to validate. If omitted, derive the version from --tag.",
    )
    validate_parser.add_argument(
        "--tag",
        help="Git tag to validate, for example v0.2.0 or v0.2.0rc1.",
    )
    validate_parser.add_argument(
        "--expected-channel",
        choices=("stable", "rc"),
        help="Require the version to target one release channel.",
    )
    validate_parser.add_argument(
        "--require-project-match",
        action="store_true",
        help="Fail unless pyproject.toml already matches the validated version.",
    )
    validate_parser.add_argument(
        "--pyproject",
        type=Path,
        default=PYPROJECT_PATH,
        help="Path to the pyproject.toml file to compare against.",
    )

    return parser


def resolve_version_argument(version: str | None, tag: str | None) -> str:
    """Resolve the version to validate from CLI arguments.

    :param version: Explicit version passed by the caller.
    :type version: str | None
    :param tag: Optional release tag.
    :type tag: str | None
    :return: Resolved version string.
    :raises ReleaseManagementError: If neither a version nor a tag is supplied.
    """
    if version is not None:
        return version
    if tag is not None:
        return extract_version_from_tag(tag)
    raise ReleaseManagementError("Provide --version, --tag, or both.")


def run_show(pyproject_path: Path) -> int:
    """Print the current project version.

    :param pyproject_path: Metadata file to inspect.
    :type pyproject_path: Path
    :return: Process exit code.
    """
    print(read_project_version(pyproject_path))
    return 0


def run_set(version: str, pyproject_path: Path) -> int:
    """Update the project version in ``pyproject.toml``.

    :param version: New version string to write.
    :type version: str
    :param pyproject_path: Metadata file to update.
    :type pyproject_path: Path
    :return: Process exit code.
    """
    previous_version, updated_version = write_project_version(version, pyproject_path)
    print(f"Updated {pyproject_path} from {previous_version} to {updated_version}.")
    return 0


def run_validate(
    *,
    version: str | None,
    tag: str | None,
    expected_channel: ReleaseChannel | None,
    require_project_match: bool,
    pyproject_path: Path,
) -> int:
    """Validate release metadata for CI or local release preparation.

    :param version: Explicit version to validate.
    :type version: str | None
    :param tag: Optional Git tag to validate.
    :type tag: str | None
    :param expected_channel: Optional required release channel.
    :type expected_channel: ReleaseChannel | None
    :param require_project_match: Whether the metadata file must already match the version.
    :type require_project_match: bool
    :param pyproject_path: Metadata file to compare against.
    :type pyproject_path: Path
    :return: Process exit code.
    """
    resolved_version = resolve_version_argument(version, tag)
    channel = validate_release_version(resolved_version, expected_channel=expected_channel)

    if tag is not None:
        ensure_version_matches_tag(resolved_version, tag)
    if require_project_match:
        ensure_project_version_matches(resolved_version, pyproject_path)

    print(
        f"Validated {channel} release version {resolved_version}"
        + (f" against tag {tag}" if tag is not None else "")
        + (f" and {pyproject_path}" if require_project_match else "")
        + "."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the release version management CLI.

    :param argv: Optional CLI argument override.
    :type argv: list[str] | None
    :return: Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "show":
            return run_show(args.pyproject)
        if args.command == "set":
            return run_set(args.version, args.pyproject)
        return run_validate(
            version=args.version,
            tag=args.tag,
            expected_channel=args.expected_channel,
            require_project_match=args.require_project_match,
            pyproject_path=args.pyproject,
        )
    except ReleaseManagementError as exc:
        parser.exit(status=1, message=f"{exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
