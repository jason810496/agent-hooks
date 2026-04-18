"""Shared helpers for packaging and release management."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

ReleaseChannel = Literal["stable", "rc"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"

_PROJECT_VERSION_PATTERN = re.compile(r'(?m)^version\s*=\s*"(?P<version>[^"]+)"\s*$')
_STABLE_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
_RC_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+rc\d+$")


class ReleaseManagementError(ValueError):
    """Represent invalid release state or input."""


def detect_release_channel(version: str) -> ReleaseChannel:
    """Detect the release channel for a project version.

    :param version: Version string to inspect.
    :type version: str
    :return: ``"stable"`` for final releases or ``"rc"`` for release candidates.
    :raises ReleaseManagementError: If the version does not match the supported patterns.
    """
    if _STABLE_VERSION_PATTERN.fullmatch(version):
        return "stable"
    if _RC_VERSION_PATTERN.fullmatch(version):
        return "rc"

    raise ReleaseManagementError("Unsupported version format. Expected 'X.Y.Z' or 'X.Y.ZrcN'.")


def validate_release_version(
    version: str,
    *,
    expected_channel: ReleaseChannel | None = None,
) -> ReleaseChannel:
    """Validate a release version and optionally enforce its channel.

    :param version: Version string to validate.
    :type version: str
    :param expected_channel: Optional required release channel.
    :type expected_channel: ReleaseChannel | None
    :return: The validated release channel.
    :raises ReleaseManagementError: If the version is invalid or does not match the channel.
    """
    channel = detect_release_channel(version)
    if expected_channel is not None and channel != expected_channel:
        raise ReleaseManagementError(
            f"Version '{version}' targets the '{channel}' channel, expected '{expected_channel}'."
        )
    return channel


def normalize_version_tag(version: str) -> str:
    """Return the canonical Git tag name for a version.

    :param version: Project version string.
    :type version: str
    :return: Canonical tag in ``v<version>`` form.
    """
    return f"v{version}"


def extract_version_from_tag(tag: str) -> str:
    """Extract a project version from a Git tag.

    :param tag: Tag name to parse.
    :type tag: str
    :return: Version contained in the tag.
    :raises ReleaseManagementError: If the tag does not start with ``v`` or is empty.
    """
    if not tag.startswith("v") or len(tag) <= 1:
        raise ReleaseManagementError("Release tags must use the form 'vX.Y.Z' or 'vX.Y.ZrcN'.")
    return tag[1:]


def read_project_version(pyproject_path: Path = PYPROJECT_PATH) -> str:
    """Read the project version from ``pyproject.toml``.

    :param pyproject_path: Path to the project metadata file.
    :type pyproject_path: Path
    :return: The version currently declared in the project metadata.
    :raises ReleaseManagementError: If the version entry cannot be found.
    """
    contents = pyproject_path.read_text(encoding="utf-8")
    match = _PROJECT_VERSION_PATTERN.search(contents)
    if match is None:
        raise ReleaseManagementError(f"Could not find a project version in {pyproject_path}.")
    return match.group("version")


def write_project_version(version: str, pyproject_path: Path = PYPROJECT_PATH) -> tuple[str, str]:
    """Replace the project version in ``pyproject.toml``.

    :param version: New version string to write.
    :type version: str
    :param pyproject_path: Path to the project metadata file.
    :type pyproject_path: Path
    :return: The previous and updated version values.
    :raises ReleaseManagementError: If the project version entry cannot be updated.
    """
    validate_release_version(version)

    contents = pyproject_path.read_text(encoding="utf-8")
    match = _PROJECT_VERSION_PATTERN.search(contents)
    if match is None:
        raise ReleaseManagementError(f"Could not find a project version in {pyproject_path}.")

    previous_version = match.group("version")
    updated_contents = _PROJECT_VERSION_PATTERN.sub(f'version = "{version}"', contents, count=1)
    pyproject_path.write_text(updated_contents, encoding="utf-8")
    return previous_version, version


def ensure_version_matches_tag(version: str, tag: str) -> None:
    """Ensure a version string and tag refer to the same release.

    :param version: Version string to compare.
    :type version: str
    :param tag: Git tag to compare.
    :type tag: str
    :return: ``None``.
    :raises ReleaseManagementError: If the version and tag do not match.
    """
    expected_tag = normalize_version_tag(version)
    if tag != expected_tag:
        raise ReleaseManagementError(
            f"Tag '{tag}' does not match version '{version}'. Expected '{expected_tag}'."
        )


def ensure_project_version_matches(
    version: str,
    pyproject_path: Path = PYPROJECT_PATH,
) -> None:
    """Ensure ``pyproject.toml`` already contains the requested version.

    :param version: Expected project version.
    :type version: str
    :param pyproject_path: Path to the project metadata file.
    :type pyproject_path: Path
    :return: ``None``.
    :raises ReleaseManagementError: If the project version differs from the expected value.
    """
    project_version = read_project_version(pyproject_path)
    if project_version != version:
        raise ReleaseManagementError(
            f"pyproject.toml declares version '{project_version}', expected '{version}'."
        )
