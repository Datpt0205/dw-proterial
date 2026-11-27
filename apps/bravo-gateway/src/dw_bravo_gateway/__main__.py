"""The gateway's composition root: settings in, a pipeline per Bravo target, one server."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import uvicorn
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dw_bravo.approval_token import ApprovalTokenVerifier, load_public_key
from dw_bravo.contract import BravoTarget
from dw_bravo_gateway.adapters.postgres import SqlLedger, SqlPauses, SqlSwitches
from dw_bravo_gateway.adapters.sqlserver import Login, SqlServerBravo
from dw_bravo_gateway.api import create_app
from dw_bravo_gateway.pipeline import WritePipeline
from dw_bravo_gateway.settings import GatewaySettings, SettingsError, TargetLogins, get_settings
from dw_bravo_gateway.targets import TargetBravo, Targets
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup


def bravo_of(logins: TargetLogins, *, encrypt: bool) -> SqlServerBravo:
    def login(user: str, password: str) -> Login:
        return Login(
            host=logins.host,
            port=logins.port,
            database=logins.database,
            user=user,
            password=password,
            encrypt=encrypt,
        )

    return SqlServerBravo(
        read=login(logins.read_user, logins.read_password.get_secret_value()),
        write=login(logins.write_user, logins.write_password.get_secret_value()),
    )


def build(settings: GatewaySettings) -> Targets:
    settings.check_startable()
    verifier = ApprovalTokenVerifier(
        {kid: load_public_key(pem) for kid, pem in settings.public_keys().items()}
    )
    assert settings.database_url is not None and settings.tenant_id is not None
    engine = create_async_engine(
        settings.database_url.get_secret_value(), pool_pre_ping=True, hide_parameters=True
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    switches = SqlSwitches(SqlRuleVersionLookup(sessions), SqlPauses(sessions))
    ledger = SqlLedger(sessions)
    reach: dict[BravoTarget, TargetBravo] = {}
    for target, logins in settings.targets().items():
        bravo = bravo_of(logins, encrypt=settings.bravo_encrypt)
        pipeline = WritePipeline(
            verifier=verifier,
            switches=switches,
            ledger=ledger,
            directory=bravo,
            rights=bravo,
            documents=bravo,
            engine=bravo,
            writer=bravo,
            now=lambda: datetime.now(UTC),
            tenant_id=settings.tenant_id,
            target=target,
        )
        reach[target] = TargetBravo(
            pipeline, orders=bravo, directory=bravo, sync=bravo, fingerprints=bravo
        )
    return Targets(settings.tenant_id, switches, reach)


def main() -> int:
    settings = get_settings()
    try:
        targets = build(settings)
    except SettingsError as refused:
        print(f"dw-bravo-gateway: not starting: {refused}", file=sys.stderr)
        return 2
    app = create_app(
        targets,
        max_request_bytes=settings.max_request_bytes,
        docs=not settings.is_deployed,
    )
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
