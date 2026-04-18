from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release.common import (  # noqa: E402
    ReleaseManagementError,
    ensure_project_version_matches,
    ensure_version_matches_tag,
    extract_version_from_tag,
    read_project_version,
    validate_release_version,
    write_project_version,
)
from scripts.release.manage_version import main  # noqa: E402


def write_pyproject(tmp_path: Path, version: str) -> Path:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        "\n".join(
            [
                "[build-system]",
                'requires = ["hatchling>=1.27.0"]',
                'build-backend = "hatchling.build"',
                "",
                "[project]",
                'name = "agent-hooks"',
                f'version = "{version}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return pyproject_path


class TestReleaseCommon:
    @pytest.mark.parametrize(
        ("version", "expected_channel"),
        [
            pytest.param("1.2.3", "stable", id="stable"),
            pytest.param("1.2.3rc4", "rc", id="release-candidate"),
        ],
    )
    def test_validate_release_version_accepts_supported_formats(
        self,
        version: str,
        expected_channel: str,
    ) -> None:
        channel = validate_release_version(version)

        assert channel == expected_channel

    @pytest.mark.parametrize(
        "version",
        [
            pytest.param("1.2", id="missing-patch"),
            pytest.param("1.2.3-rc1", id="hyphenated-rc"),
            pytest.param("v1.2.3", id="tag-format"),
        ],
    )
    def test_validate_release_version_rejects_invalid_formats(self, version: str) -> None:
        with pytest.raises(ReleaseManagementError, match="Unsupported version format"):
            validate_release_version(version)

    def test_extract_version_from_tag_requires_v_prefix(self) -> None:
        with pytest.raises(ReleaseManagementError, match="Release tags must use the form"):
            extract_version_from_tag("1.2.3")

    def test_write_project_version_rewrites_pyproject(self, tmp_path: Path) -> None:
        pyproject_path = write_pyproject(tmp_path, "0.1.0")

        previous_version, updated_version = write_project_version("0.2.0rc1", pyproject_path)

        assert previous_version == "0.1.0"
        assert updated_version == "0.2.0rc1"
        assert read_project_version(pyproject_path) == "0.2.0rc1"

    def test_ensure_version_matches_tag_rejects_mismatches(self) -> None:
        with pytest.raises(ReleaseManagementError, match="does not match version"):
            ensure_version_matches_tag("0.2.0", "v0.2.1")

    def test_ensure_project_version_matches_rejects_mismatches(self, tmp_path: Path) -> None:
        pyproject_path = write_pyproject(tmp_path, "0.1.0")

        with pytest.raises(ReleaseManagementError, match="pyproject.toml declares version"):
            ensure_project_version_matches("0.2.0", pyproject_path)


class TestManageVersionCli:
    def test_show_command_prints_project_version(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        pyproject_path = write_pyproject(tmp_path, "0.3.0")

        exit_code = main(["show", "--pyproject", str(pyproject_path)])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == "0.3.0"

    def test_set_command_updates_pyproject(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        pyproject_path = write_pyproject(tmp_path, "0.3.0rc1")

        exit_code = main(["set", "--version", "0.3.0", "--pyproject", str(pyproject_path)])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Updated" in captured.out
        assert read_project_version(pyproject_path) == "0.3.0"

    def test_validate_command_accepts_matching_tag_and_project(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        pyproject_path = write_pyproject(tmp_path, "0.4.0rc2")

        exit_code = main(
            [
                "validate",
                "--tag",
                "v0.4.0rc2",
                "--expected-channel",
                "rc",
                "--require-project-match",
                "--pyproject",
                str(pyproject_path),
            ]
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Validated rc release version 0.4.0rc2" in captured.out

    def test_validate_command_exits_for_channel_mismatch(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        pyproject_path = write_pyproject(tmp_path, "0.4.0rc2")

        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "validate",
                    "--tag",
                    "v0.4.0rc2",
                    "--expected-channel",
                    "stable",
                    "--require-project-match",
                    "--pyproject",
                    str(pyproject_path),
                ]
            )

        captured = capsys.readouterr()
        assert exc_info.value.code == 1
        assert "expected 'stable'" in captured.err
