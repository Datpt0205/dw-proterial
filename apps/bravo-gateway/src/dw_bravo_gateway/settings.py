"""Every environment knob the Bravo gateway reads, in one place (ticket 63).

The gateway holds Bravo's two logins and nothing else of value. Where it is
deployed (`uat`, `production`), it refuses to start without the approval
verifying key: a gateway that verifies nothing would refuse every write, and
one started by mistake must say so at once, not at a PIC's first write.
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEPLOYED_PROFILES: frozenset[str] = frozenset({"uat", "production"})


class SettingsError(RuntimeError):
    """The gateway may not start with these settings."""


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
    bravo_host: str = ""
    bravo_port: int = 1433
    bravo_database: str = ""
    bravo_read_user: str = ""
    bravo_read_password: SecretStr = SecretStr("")
    bravo_write_user: str = ""
    bravo_write_password: SecretStr = SecretStr("")
    # Bravo's server supports encryption and its clients do not ask for it
    # (11-20 survey); the gateway asks.
    bravo_encrypt: bool = True
    # Which Bravo this gateway reads: its fingerprint is labelled with it,
    # and the watch compares UAT with production (ticket 65).
    environment: Literal["uat", "production"] = "production"
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

    def check_startable(self) -> None:
        """Refuse to start rather than run half-configured."""
        missing = [
            name
            for name, value in (
                ("TENANT_ID", self.tenant_id),
                ("DATABASE_URL", self.database_url and self.database_url.get_secret_value()),
                ("BRAVO_HOST", self.bravo_host),
                ("BRAVO_DATABASE", self.bravo_database),
                ("BRAVO_READ_USER", self.bravo_read_user),
                ("BRAVO_READ_PASSWORD", self.bravo_read_password.get_secret_value()),
                ("BRAVO_WRITE_USER", self.bravo_write_user),
                ("BRAVO_WRITE_PASSWORD", self.bravo_write_password.get_secret_value()),
            )
            if not value
        ]
        if missing:
            raise SettingsError(
                "the Bravo gateway needs " + ", ".join(f"DW_BRAVO_GATEWAY_{m}" for m in missing)
            )
        if self.bravo_read_user == self.bravo_write_user:
            raise SettingsError("reads and writes use two Bravo logins (ADR 0027)")
        if self.is_deployed and not self.public_keys():
            raise SettingsError(
                "deployed without DW_BRAVO_GATEWAY_APPROVAL_PUBLIC_KEYS: no write could be verified"
            )
        if self.is_deployed and not self.bravo_encrypt:
            raise SettingsError("deployed, the gateway asks Bravo for an encrypted connection")


@lru_cache
def get_settings() -> GatewaySettings:
    return GatewaySettings()
