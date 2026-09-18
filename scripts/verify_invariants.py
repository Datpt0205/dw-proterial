"""Check the three invariants this repository has actually broken.

Not a linter and not a generic security scanner — both already run in CI and
neither would have caught any of these. Each check below exists because the
failure it looks for happened here, was expensive to find, and is mechanical to
detect. The counts are from `.claude/rules/failure-modes.md`.

1. A tenant-scoped table without row-level security. Grants are inherited from
   `ALTER DEFAULT PRIVILEGES`; RLS is not, and a tenant table without it is a
   cross-tenant read waiting to happen. Nothing enforced this before migration
   0007 went in with RLS only because it was remembered.

2. A field declared on a contract and read by nothing (found 9 times). `autonomy_level`
   was declared, validated and read nowhere, so a worker at A4 paused as often as
   one at A0. A control that is configured and unenforced reads like a safeguard
   in review and is discovered to be decoration by the first incident.

3. A value a `Literal` accepts that no code branches on (found 4 times). The schema
   took `approval_policy: conditional`, no branch matched it, and it silently
   behaved as `never` — so anyone who wrote it expecting a gate got none.

Usage: uv run python scripts/verify_invariants.py
Exit 0 clean, 1 violations.

Every check has an escape hatch with a mandatory reason. A checker with no way to
say "this one is deliberate" gets deleted the first time it is wrong, and then
none of it runs.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- check 1 --

MIGRATIONS = REPO_ROOT / "db" / "migrations"

# Tables that hold a `tenant_id` and deliberately have no policy of their own.
# Empty today; an entry must say why, not merely that.
RLS_EXEMPT: dict[tuple[str, str], str] = {}


def _migration_text() -> str:
    parts = [
        path.read_text(encoding="utf-8")
        for path in sorted(MIGRATIONS.rglob("*"))
        if path.suffix in {".py", ".sql"} and path.name != "__init__.py"
    ]
    return "\n".join(parts)


def check_tenant_tables_have_rls() -> list[str]:
    text = _migration_text()
    # Both spellings the migrations use: a `);` terminated block in the baseline
    # dump, and an indented `)` inside a Python string literal.
    found: dict[tuple[str, str], str] = {}
    for pattern in (
        r"CREATE TABLE (\w+)\.(\w+) \(([^;]*?)\n\);",
        r"CREATE TABLE (\w+)\.(\w+) \(([^;]*?)\n\s*\)",
    ):
        for schema, name, body in re.findall(pattern, text, re.S):
            found.setdefault((schema, name), body)

    violations = []
    for (schema, name), body in sorted(found.items()):
        if "tenant_id" not in body or (schema, name) in RLS_EXEMPT:
            continue
        missing = [
            label
            for label, present in (
                ("ENABLE ROW LEVEL SECURITY", f"ALTER TABLE {schema}.{name} ENABLE ROW" in text),
                (
                    "FORCE ROW LEVEL SECURITY",
                    f"ALTER TABLE ONLY {schema}.{name} FORCE ROW" in text
                    or f"ALTER TABLE {schema}.{name} FORCE ROW" in text,
                ),
                (
                    "a tenant policy",
                    re.search(rf"CREATE POLICY \w+ ON {schema}\.{name}\b", text) is not None,
                ),
            )
            if not present
        ]
        if missing:
            violations.append(f"{schema}.{name} holds tenant_id but has no {', no '.join(missing)}")
    return violations


# ------------------------------------------------------------- checks 2, 3 --

# The contracts whose fields decide behaviour. Listed explicitly rather than
# discovered: a repo-wide sweep would flag DTO fields that exist only to be
# serialised, and a check that cries wolf is a check that gets switched off.
WATCHED_CONTRACTS: dict[str, tuple[str, ...]] = {
    "packages/python/dw_agent_runtime/src/dw_agent_runtime/contracts.py": (
        "WorkerDefinition",
        "ToolDefinition",
        "RunContext",
    ),
    "packages/python/dw_memory/src/dw_memory/contracts.py": ("MemoryItem",),
}

# `Literal` aliases whose values are decisions, not labels.
WATCHED_LITERALS: tuple[str, ...] = (
    "packages/python/dw_agent_runtime/src/dw_agent_runtime/contracts.py",
    "packages/python/dw_kernel/src/dw_kernel/autonomy.py",
)

# name -> why it is allowed to be unread. Empty today.
UNREAD_EXEMPT: dict[str, str] = {}


def _python_sources() -> dict[Path, str]:
    sources: dict[Path, str] = {}
    for directory in ("packages/python", "apps", "scripts"):
        for path in (REPO_ROOT / directory).rglob("*.py"):
            if ".venv" in path.parts or "__pycache__" in path.parts:
                continue
            sources[path] = path.read_text(encoding="utf-8")
    return sources


def _referenced_elsewhere(sources: dict[Path, str], owner: Path, needle: str) -> bool:
    return any(path != owner and re.search(needle, text) for path, text in sources.items())


def check_declared_fields_are_read(sources: dict[Path, str]) -> list[str]:
    violations = []
    for relative, classes in WATCHED_CONTRACTS.items():
        owner = REPO_ROOT / relative
        tree = ast.parse(sources[owner])
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name not in classes:
                continue
            for statement in node.body:
                if not isinstance(statement, ast.AnnAssign):
                    continue
                if not isinstance(statement.target, ast.Name):
                    continue
                field = statement.target.id
                if field.startswith("_") or field == "model_config":
                    continue
                key = f"{node.name}.{field}"
                if key in UNREAD_EXEMPT:
                    continue
                if not _referenced_elsewhere(sources, owner, rf"\b{re.escape(field)}\b"):
                    violations.append(f"{key} is declared and read nowhere outside {relative}")
    return violations


def check_literal_values_are_handled(sources: dict[Path, str]) -> list[str]:
    violations = []
    for relative in WATCHED_LITERALS:
        owner = REPO_ROOT / relative
        for match in re.finditer(r"^(\w+) = Literal\[([^\]]+)\]", sources[owner], re.M):
            alias, body = match.group(1), match.group(2)
            for value in re.findall(r'"([^"]+)"', body):
                key = f"{alias}:{value}"
                if key in UNREAD_EXEMPT:
                    continue
                if not _referenced_elsewhere(sources, owner, re.escape(f'"{value}"')):
                    violations.append(
                        f"{alias} accepts {value!r} and no code outside {relative} mentions it"
                    )
    return violations


def main() -> int:
    sources = _python_sources()
    checks = (
        ("tenant tables have row-level security", check_tenant_tables_have_rls()),
        ("declared fields are read", check_declared_fields_are_read(sources)),
        ("literal values are handled", check_literal_values_are_handled(sources)),
    )
    failed = False
    for label, violations in checks:
        if violations:
            failed = True
            print(f"FAILED: {label}", file=sys.stderr)
            for violation in violations:
                print(f"  - {violation}", file=sys.stderr)
        else:
            print(f"ok: {label}")
    if failed:
        print(
            "\nIf a violation is deliberate, add it to the exemption map in this file"
            " with the reason — not a bare silence.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
