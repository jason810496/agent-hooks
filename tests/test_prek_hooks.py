from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Protocol, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREK_SCRIPTS = ROOT / "scripts" / "prek"

if str(PREK_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PREK_SCRIPTS))


class HookModule(Protocol):
    def check_file(self, path: Path) -> list[str]:
        """Validate a single file.

        :param path: File to validate.
        :type path: Path
        :return: Validation errors.
        :rtype: list[str]
        """
        ...

    def main(self, argv: list[str] | None = None) -> int:
        """Execute the hook entrypoint.

        :param argv: Optional CLI argument override.
        :type argv: list[str] | None
        :return: Process exit code.
        :rtype: int
        """
        ...


def load_module(module_name: str, relative_path: str) -> object:
    """Load a hook module from disk for direct unit testing.

    :param module_name: Synthetic module name used for loading.
    :type module_name: str
    :param relative_path: Path relative to the repository root.
    :type relative_path: str
    :return: Imported module object.
    """
    module_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        msg = f"Could not load module from {module_path}"
        raise RuntimeError(msg)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NO_STDOUT_PRINTS = cast(
    HookModule,
    load_module(
        "check_no_stdout_prints_module",
        "scripts/prek/check_no_stdout_prints.py",
    ),
)


class TestCheckNoStdoutPrints:
    @pytest.mark.parametrize(
        ("source_text", "expected_errors"),
        [
            pytest.param(
                'import sys\nprint("debug", file=sys.stderr)\n',
                [],
                id="stderr-only-print-is-allowed",
            ),
            pytest.param(
                'print("debug")\n',
                ["avoid print() in hook source"],
                id="stdout-print-is-rejected",
            ),
        ],
    )
    def test_check_file(self, tmp_path: Path, source_text: str, expected_errors: list[str]) -> None:
        path = tmp_path / "candidate.py"
        path.write_text(source_text, encoding="utf-8")

        errors = NO_STDOUT_PRINTS.check_file(path)

        if not expected_errors:
            assert errors == []
            return

        assert len(errors) == len(expected_errors)
        assert expected_errors[0] in errors[0]

    @pytest.mark.parametrize(
        ("source_text", "expected_exit_code"),
        [
            pytest.param("x = 1\n", 0, id="clean-source"),
            pytest.param('print("debug")\n', 1, id="invalid-source"),
        ],
    )
    def test_main(self, tmp_path: Path, source_text: str, expected_exit_code: int) -> None:
        path = tmp_path / "candidate.py"
        path.write_text(source_text, encoding="utf-8")

        result = NO_STDOUT_PRINTS.main([str(path)])

        assert result == expected_exit_code
