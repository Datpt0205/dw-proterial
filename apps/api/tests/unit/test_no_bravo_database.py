"""Only the Bravo gateway reaches Bravo's database (ADR 0027, superseding
ADR 0026; sales ticket 63, acceptance 1). `scripts/verify_architecture.py`
refuses a SQL Server driver wherever else it could enter: imported by a
package, declared by one, named in a connection URL, or locked in `uv.lock`
for anything but the gateway."""

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
def test_a_sql_server_driver_outside_the_gateway_is_refused(
    tmp_path: Path, source: str, dependency: str, lock: str
) -> None:
    _package(tmp_path, source=source, dependency=dependency)
    (tmp_path / "uv.lock").write_text(f"version = 1\n[[package]]\n{lock}", encoding="utf-8")

    found = _load_script().bravo_database_violations(tmp_path)

    assert len(found) == 1 and "ADR 0027" in found[0]


def _gateway(root: Path, *, source: str = "", dependency: str = "") -> None:
    gateway = root / "apps" / "bravo-gateway"
    (gateway / "src" / "dw_bravo_gateway").mkdir(parents=True)
    (gateway / "pyproject.toml").write_text(
        f'[project]\nname = "dw-bravo-gateway"\ndependencies = [{dependency}]\n',
        encoding="utf-8",
    )
    (gateway / "src" / "dw_bravo_gateway" / "bravo.py").write_text(source, encoding="utf-8")


def _lock(root: Path, *dependents: str) -> None:
    entries = "".join(
        f'[[package]]\nname = "{name}"\ndependencies = [{{ name = "pymssql" }}]\n'
        for name in dependents
    )
    (root / "uv.lock").write_text(
        f'version = 1\n[[package]]\nname = "pymssql"\n{entries}', encoding="utf-8"
    )


def test_the_gateway_may_import_declare_lock_and_name_a_driver(tmp_path: Path) -> None:
    _gateway(
        tmp_path,
        # Spelled in two parts so this file names no URL itself.
        source='import pymssql\nURL = "mssql' + '+pymssql://bravo/db"\n',
        dependency='"pymssql==2.3.0"',
    )
    _lock(tmp_path, "dw-bravo-gateway")

    assert _load_script().bravo_database_violations(tmp_path) == []


@pytest.mark.parametrize(
    "dependents",
    [("dw-bravo-gateway", "dw-sales"), ("some-library",), ()],
    ids=["gateway_and_a_context", "a_library_pulls_it_in", "nothing_declares_it"],
)
def test_a_locked_driver_is_refused_unless_the_gateway_is_its_one_dependent(
    tmp_path: Path, dependents: tuple[str, ...]
) -> None:
    _gateway(tmp_path, dependency='"pymssql==2.3.0"')
    _lock(tmp_path, *dependents)

    found = _load_script().bravo_database_violations(tmp_path)

    assert len(found) == 1 and "uv.lock locks 'pymssql'" in found[0]


def test_a_gateway_lookalike_path_is_not_the_gateway(tmp_path: Path) -> None:
    lookalike = tmp_path / "apps" / "bravo-gateway-tools" / "src" / "x"
    lookalike.mkdir(parents=True)
    (lookalike / "probe.py").write_text("import pyodbc\n", encoding="utf-8")

    found = _load_script().bravo_database_violations(tmp_path)

    assert len(found) == 1 and "imports 'pyodbc'" in found[0]
