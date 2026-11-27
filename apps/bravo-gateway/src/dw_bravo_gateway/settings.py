"""Every environment knob the Bravo gateway reads, in one place (ticket 63).

The gateway holds Bravo's logins and nothing else of value. Where it is
deployed (`uat`, `production`), it refuses to start without the approval
verifying key: a gateway that verifies nothing would refuse every write, and
one started by mistake must say so at once, not at a PIC's first write.

Two Bravos, one credential set each (ticket 85): `DW_BRAVO_GATEWAY_UAT_*`
and `DW_BRAVO_GATEWAY_PRODUCTION_*`. Which one a write goes to is the
tenant's rule, not this file; a target with no credentials here is absent,
and the gateway refuses every read and write while the tenant's rule names
it, never falling back to the other.

The single set before ticket 85 (`DW_BRAVO_GATEWAY_BRAVO_*`) refuses to
start. Its Bravo was named by `DW_BRAVO_GATEWAY_ENVIRONMENT`, `production`
unless set, so it may hold the company's real Bravo: read as either target
it could be labelled the wrong one, and the target guard compares labels.
Whoever holds it moves it to the prefix of the Bravo it names (ticket 85
review).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from dw_bravo.contract import BravoTarget

DEPLOYED_PROFILES: frozenset[str] = frozenset({"uat", "production"})


class SettingsError(RuntimeError):
    """The gateway may not start with these settings."""


@dataclass(frozen=True)
class TargetLogins:
    """One Bravo database and the two logins DW holds on it (ADR 0027)."""

    host: str
    port: int
    database: str
    read_user: str
    read_password: SecretStr
    write_user: str
    write_password: SecretStr


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DW_BRAVO_GATEWAY_", extra="ignore", populate_by_name=True
    )

    profile: Literal["local", "test", "uat", "production"] = Field(
        default="local",
        validation_alias=AliasChoices("DW_BRAVO_GATEWAY_PROFILE", "DW_API_PROFILE"),
    )
    # The DW tenant whose Bravo this is (one gateway per Bravo): any other
    # tenant's approval is refused.
    tenant_id: uuid.UUID | None = None

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _unset_when_empty(cls, value: object) -> object:
        # Compose passes an unset variable as "" (`${VAR:-}`): not configured.
        return None if value == "" else value

    # {key id: Ed25519 public key PEM}, as JSON: the approval path's keys.
    approval_public_keys: SecretStr = SecretStr("{}")
    # DW's PostgreSQL as `dw_app` (RLS applies): the ledger and the switches.
    database_url: SecretStr | None = None
    # Bravo UAT (`B8_Hitachi_Cable_UAT`, trace 3).
    uat_host: str = ""
    uat_port: int = 1433
    uat_database: str = ""
    uat_read_user: str = ""
    uat_read_password: SecretStr = SecretStr("")
    uat_write_user: str = ""
    uat_write_password: SecretStr = SecretStr("")
    # The Bravo the company runs on (`B8_Hitachi_Cable`, 11-19 survey).
    production_host: str = ""
    production_port: int = 1433
    production_database: str = ""
    production_read_user: str = ""
    production_read_password: SecretStr = SecretStr("")
    production_write_user: str = ""
    production_write_password: SecretStr = SecretStr("")
    # Before ticket 85: one set, named by an `environment` that defaulted to
    # production. Read only to refuse it (`targets`).
    bravo_host: str = ""
    bravo_port: int = 1433
    bravo_database: str = ""
    bravo_read_user: str = ""
    bravo_read_password: SecretStr = SecretStr("")
    bravo_write_user: str = ""
    bravo_write_password: SecretStr = SecretStr("")
    # Bravo's server supports encryption and its clients do not ask for it
    # (11-20 survey); the gateway asks, of both targets.
    bravo_encrypt: bool = True
    port: int = 8080
    max_request_bytes: int = 64 * 1024

    @property
    def is_deployed(self) -> bool:
        return self.profile in DEPLOYED_PROFILES

    def public_keys(self) -> dict[str, str]:
        try:
            keys = json.loads(self.approval_public_keys.get_secret_value())
        except json.JSONDecodeError:
            raise SettingsError("DW_BRAVO_GATEWAY_APPROVAL_PUBLIC_KEYS is not JSON") from None
        if not isinstance(keys, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in keys.items()
        ):
            raise SettingsError("DW_BRAVO_GATEWAY_APPROVAL_PUBLIC_KEYS is {key id: PEM}")
        return keys

    def _set(self, prefix: str) -> dict[str, object]:
        return {
            name: getattr(self, f"{prefix}_{name}")
            for name in (
                "host",
                "port",
                "database",
                "read_user",
                "read_password",
                "write_user",
                "write_password",
            )
        }

    def _sets(self) -> dict[BravoTarget, tuple[str, dict[str, object]]]:
        """Each target's fields and the variable prefix they came from."""
        if _has_credentials(self._set("bravo")):
            raise SettingsError(
                "DW_BRAVO_GATEWAY_BRAVO_* is the single set before ticket 85, whose Bravo"
                " DW_BRAVO_GATEWAY_ENVIRONMENT named (production unless set): move it to"
                " DW_BRAVO_GATEWAY_UAT_* or DW_BRAVO_GATEWAY_PRODUCTION_*, the one it names"
            )
        return {
            "uat": ("UAT", self._set("uat")),
            "production": ("PRODUCTION", self._set("production")),
        }

    def targets(self) -> dict[BravoTarget, TargetLogins]:
        """Every target with credentials; one half-configured refuses."""
        found: dict[BravoTarget, TargetLogins] = {}
        for target, (prefix, fields) in self._sets().items():
            if not _has_credentials(fields):
                continue  # absent: refused at every read and write naming it
            missing = [name.upper() for name, value in fields.items() if not _value(value)]
            if missing:
                raise SettingsError(
                    f"the {target} Bravo needs "
                    + ", ".join(f"DW_BRAVO_GATEWAY_{prefix}_{m}" for m in missing)
                )
            logins = TargetLogins(**fields)  # type: ignore[arg-type]
            if logins.read_user == logins.write_user:
                raise SettingsError(
                    f"the {target} Bravo: reads and writes use two logins (ADR 0027)"
                )
            found[target] = logins
        return found

    def check_startable(self) -> None:
        """Refuse to start rather than run half-configured."""
        missing = [
            name
            for name, value in (
                ("TENANT_ID", self.tenant_id),
                ("DATABASE_URL", self.database_url and self.database_url.get_secret_value()),
            )
            if not value
        ]
        if missing:
            raise SettingsError(
                "the Bravo gateway needs " + ", ".join(f"DW_BRAVO_GATEWAY_{m}" for m in missing)
            )
        if not self.targets():
            raise SettingsError(
                "the Bravo gateway needs the logins of at least one Bravo:"
                " DW_BRAVO_GATEWAY_UAT_* or DW_BRAVO_GATEWAY_PRODUCTION_*"
            )
        if self.is_deployed and not self.public_keys():
            raise SettingsError(
                "deployed without DW_BRAVO_GATEWAY_APPROVAL_PUBLIC_KEYS: no write could be verified"
            )
        if self.is_deployed and not self.bravo_encrypt:
            raise SettingsError("deployed, the gateway asks Bravo for an encrypted connection")


# What makes a target present: any of its logins. A database name alone is
# not (`.env.example` names both databases and holds no credential).
_CREDENTIALS = ("host", "read_user", "read_password", "write_user", "write_password")


def _value(value: object) -> object:
    return value.get_secret_value() if isinstance(value, SecretStr) else value


def _has_credentials(fields: dict[str, object]) -> bool:
    return any(_value(fields[name]) for name in _CREDENTIALS)


@lru_cache
def get_settings() -> GatewaySettings:
    return GatewaySettings()
