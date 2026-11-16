"""DW never connects to Bravo's database, not even read-only (ADR 0026;
dw_sales ticket 14, acceptance 3). `scripts/verify_architecture.py` refuses
a SQL Server driver wherever it could enter: imported by a package, declared
by one, locked in `uv.lock`, or named in a connection URL."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_script() -> Any:  # scripts/ is not a package; load by path
    spec = importlib.util.spec_from_file_location(
        "verify_architecture", REPO_ROOT / "scripts" / "verify_architecture.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_architecture"] = module
    spec.loader.exec_module(module)
    return module


def _package(root: Path, *, source: str = "", dependency: str = "") -> Path:
    package = root / "packages" / "python" / "dw_x"
    (package / "src" / "dw_x" / "testing").mkdir(parents=True)
    (package / "pyproject.toml").write_text(
        f'[project]\nname = "dw-x"\ndependencies = [{dependency}]\n', encoding="utf-8"
    )
    # Under `testing`, which the declared-dependency check leaves out: this
    # one does not.
    (package / "src" / "dw_x" / "testing" / "bravo.py").write_text(source, encoding="utf-8")
    return package


def test_the_repository_has_no_way_into_bravos_database() -> None:
    assert _load_script().bravo_database_violations(REPO_ROOT) == []


@pytest.mark.parametrize(
    ("source", "dependency", "lock"),
    [
        ("import pyodbc\n", "", ""),
        ("from pymssql import connect\n", "", ""),
        ("", '"aioodbc>=0.5"', ""),
        ("", "", 'name = "python-tds"\n'),
        # Spelled in two parts so this file names no URL itself.
        ('URL = "mssql' + '+pyodbc://bravo/db"\n', "", ""),
    ],
    ids=["import", "from_import", "declared", "locked", "url"],
)
def test_a_sql_server_driver_anywhere_is_refused(
    tmp_path: Path, source: str, dependency: str, lock: str
) -> None:
    _package(tmp_path, source=source, dependency=dependency)
    (tmp_path / "uv.lock").write_text(f"version = 1\n[[package]]\n{lock}", encoding="utf-8")

    found = _load_script().bravo_database_violations(tmp_path)

    assert len(found) == 1 and "ADR 0026" in found[0]
