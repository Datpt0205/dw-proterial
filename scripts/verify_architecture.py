"""Verify that every workspace package only imports what it declares.

Complements import-linter: import-linter enforces direction/boundaries between
known modules, this script enforces that no package "borrows" a third-party or
workspace dependency it has not declared in its own pyproject.

Usage: uv run python scripts/verify_architecture.py
Exit code 0 = clean, 1 = violations found.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Import name -> distribution name for third-party packages we use.
IMPORT_TO_DIST = {
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "fastapi": "fastapi",
    "starlette": "fastapi",  # starlette ships with fastapi's dependency tree
    "uvicorn": "uvicorn",
    "sqlalchemy": "sqlalchemy",
    "alembic": "alembic",
    "asyncpg": "asyncpg",
    "langgraph": "langgraph",
    "qdrant_client": "qdrant-client",
    "redis": "redis",
    "httpx": "httpx",
    "websockets": "websockets",
    "minio": "minio",
    "boto3": "boto3",
    "opentelemetry": "opentelemetry-api",
    "prometheus_client": "prometheus-client",
    "langfuse": "langfuse",
    "jwt": "pyjwt",
    "yaml": "pyyaml",
    "deepagents": "deepagents",
    "playwright": "playwright",
    "reportlab": "reportlab",
    "openpyxl": "openpyxl",
    "pypdf": "pypdf",
    "msoffcrypto": "msoffcrypto-tool",
    "PIL": "pillow",
    # Web Push (Sales ticket 48): the sender, its VAPID key, the key's curve.
    "pywebpush": "pywebpush",
    "py_vapid": "py-vapid",
    "cryptography": "cryptography",
    "langchain": "langchain",
    "langchain_core": "langchain-core",
    "langchain_openai": "langchain-openai",
    "dw_kernel": "dw-kernel",
    "dw_platform": "dw-platform",
    "dw_agent_runtime": "dw-agent-runtime",
    "dw_knowledge": "dw-knowledge",
    "dw_memory": "dw-memory",
    "dw_connectors": "dw-connectors",
    "dw_bravo": "dw-bravo",
    "dw_observability": "dw-observability",
    "dw_evals": "dw-evals",
    "dw_api": "dw-api",
    "dw_worker": "dw-worker",
    "dw_docgen": "dw-docgen",
    "dw_purchasing": "dw-purchasing",
    "dw_reader": "dw-reader",
    "dw_sales": "dw-sales",
}


# ADR 0027 (supersedes 0026): one process holds a way into Bravo's SQL Server,
# the gateway. A driver may be imported, declared or named in a URL inside
# `apps/bravo-gateway` only, and `uv.lock` may lock one only while the gateway
# is the one package that depends on it: a library pulling a driver in
# transitively is a second door, whoever declared it. Tests and `testing`
# helpers elsewhere are refused like any other file.
# Import name -> distribution name.
SQL_SERVER_DRIVERS = {
    "pyodbc": "pyodbc",
    "pymssql": "pymssql",
    "aioodbc": "aioodbc",
    "pytds": "python-tds",
    "mssql_python": "mssql-python",
    "aiomssql": "aiomssql",
}
_SQL_SERVER_URL = "mssql+"
BRAVO_GATEWAY = Path("apps") / "bravo-gateway"
BRAVO_GATEWAY_DIST = "dw-bravo-gateway"
_RULE = "ADR 0027: only apps/bravo-gateway reaches Bravo's database"


def _inside_gateway(root: Path, path: Path) -> bool:
    return path.is_relative_to(root / BRAVO_GATEWAY)


def bravo_database_violations(root: Path) -> list[str]:
    """Every way into a SQL Server database outside the gateway (`SQL_SERVER_DRIVERS`)."""
    found: list[str] = []
    dists = set(SQL_SERVER_DRIVERS.values())
    for base in (root / "packages", root / "apps"):
        if not base.is_dir():
            continue
        for pyproject in base.rglob("pyproject.toml"):
            if "node_modules" in pyproject.parts or _inside_gateway(root, pyproject):
                continue
            for name in sorted(declared_dependencies(pyproject) & dists):
                found.append(f"{pyproject.relative_to(root)} declares {name!r} ({_RULE})")
        for py_file in base.rglob("*.py"):
            if "node_modules" in py_file.parts or _inside_gateway(root, py_file):
                continue
            text = py_file.read_text(encoding="utf-8", errors="replace")
            if _SQL_SERVER_URL in text and py_file.name != Path(__file__).name:
                found.append(f"{py_file.relative_to(root)} names a SQL Server URL ({_RULE})")
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module]
                    if isinstance(node, ast.ImportFrom) and node.module
                    else []
                )
                for module in names:
                    if module.split(".")[0] in SQL_SERVER_DRIVERS:
                        found.append(f"{py_file.relative_to(root)} imports {module!r} ({_RULE})")
    found.extend(_locked_drivers(root / "uv.lock", dists))
    return found


def _locked_drivers(lock: Path, dists: set[str]) -> list[str]:
    """A locked driver is allowed only while the gateway is its one dependent."""
    if not lock.exists():
        return []
    packages = tomllib.loads(lock.read_text(encoding="utf-8")).get("package", [])
    found: list[str] = []
    for driver in sorted(dists & {p.get("name") for p in packages}):
        dependents = sorted(
            p["name"]
            for p in packages
            if any(d.get("name") == driver for d in p.get("dependencies", []))
            or any(
                d.get("name") == driver
                for group in p.get("optional-dependencies", {}).values()
                for d in group
            )
        )
        if dependents != [BRAVO_GATEWAY_DIST]:
            found.append(
                f"uv.lock locks {driver!r} for {dependents or ['nothing that declares it']}"
                f" ({_RULE})"
            )
    return found


def declared_dependencies(pyproject: Path) -> set[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps: set[str] = set()
    project = data.get("project", {})
    specs = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        specs.extend(group)
    for spec in specs:
        name = (
            spec.split("[")[0]
            .split(">")[0]
            .split("<")[0]
            .split("=")[0]
            .split("!")[0]
            .split(";")[0]
            .strip()
        )
        deps.add(name.lower())
    return deps


def imported_top_levels(src_dir: Path) -> dict[str, list[Path]]:
    imports: dict[str, list[Path]] = {}
    for py_file in src_dir.rglob("*.py"):
        # `testing` subpackages hold test-support helpers (e.g. the seed used by
        # every context's integration tests). Like the tests they serve, they
        # legitimately compose several bounded contexts and cannot declare those
        # as runtime dependencies without inverting the layering, so they are
        # exempt from the declared-dependency check.
        if "testing" in py_file.relative_to(src_dir).parts:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover — parse errors fail loudly
            print(f"SYNTAX ERROR in {py_file}: {exc}")
            sys.exit(1)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.setdefault(alias.name.split(".")[0], []).append(py_file)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.setdefault(node.module.split(".")[0], []).append(py_file)
    return imports


def check_package(package_dir: Path) -> list[str]:
    pyproject = package_dir / "pyproject.toml"
    src_dir = package_dir / "src"
    if not pyproject.exists() or not src_dir.exists():
        return []

    own_modules = {p.name for p in src_dir.iterdir() if p.is_dir()}
    declared = declared_dependencies(pyproject)
    violations: list[str] = []

    for module, files in sorted(imported_top_levels(src_dir).items()):
        if module in own_modules or module in sys.stdlib_module_names:
            continue
        dist = IMPORT_TO_DIST.get(module)
        if dist is None:
            violations.append(
                f"{package_dir.name}: unknown third-party import {module!r} "
                f"(add to IMPORT_TO_DIST) in {files[0].relative_to(REPO_ROOT)}"
            )
        elif dist.lower() not in declared:
            violations.append(
                f"{package_dir.name}: imports {module!r} but does not declare "
                f"{dist!r} in {pyproject.relative_to(REPO_ROOT)} "
                f"(first seen in {files[0].relative_to(REPO_ROOT)})"
            )
    return violations


def main() -> int:
    package_dirs = sorted(
        [
            *(REPO_ROOT / "packages" / "python").iterdir(),
            REPO_ROOT / "apps" / "api",
            REPO_ROOT / "apps" / "chat",
            REPO_ROOT / "apps" / "docgen",
            REPO_ROOT / "apps" / "reader",
            REPO_ROOT / "apps" / "worker",
        ]
    )
    all_violations: list[str] = []
    checked = 0
    for package_dir in package_dirs:
        if package_dir.is_dir():
            all_violations.extend(check_package(package_dir))
            checked += 1

    all_violations.extend(bravo_database_violations(REPO_ROOT))
    if all_violations:
        print(f"Declared-dependency check FAILED ({len(all_violations)} violations):")
        for violation in all_violations:
            print(f"  - {violation}")
        return 1
    print(f"Declared-dependency check passed for {checked} packages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
