"""`RoleCatalogPort` in memory, for unit tests and evals: the roles and
permission sets a test names, each with its scopes, as `platform.roles` and
`platform.permission_sets` hold them. Empty unless a test names some: the
catalog is the platform's data, and this package types none of it out."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CatalogRow:
    key: str
    name: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class StaticRoleCatalog:
    roles: tuple[CatalogRow, ...] = ()
    permission_sets: tuple[CatalogRow, ...] = ()

    async def list_roles(self) -> list[CatalogRow]:
        return sorted(self.roles, key=lambda row: row.key)

    async def list_permission_sets(self) -> list[CatalogRow]:
        return sorted(self.permission_sets, key=lambda row: row.key)
