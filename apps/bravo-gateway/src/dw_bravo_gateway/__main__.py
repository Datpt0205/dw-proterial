"""The gateway's composition root: settings in, one pipeline, one server."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import uvicorn
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from dw_bravo.approval_token import ApprovalTokenVerifier, load_public_key
from dw_bravo_gateway.adapters.postgres import SqlLedger, SqlPauses, SqlSwitches
from dw_bravo_gateway.adapters.sqlserver import Login, SqlServerBravo
from dw_bravo_gateway.api import create_app
from dw_bravo_gateway.pipeline import WritePipeline
from dw_bravo_gateway.settings import GatewaySettings, SettingsError, get_settings
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup


def build(settings: GatewaySettings) -> tuple[WritePipeline, SqlServerBravo]:
    settings.check_startable()
    verifier = ApprovalTokenVerifier(
        {kid: load_public_key(pem) for kid, pem in settings.public_keys().items()}
    )
    assert settings.database_url is not None and settings.tenant_id is not None
    engine = create_async_engine(
        settings.database_url.get_secret_value(), pool_pre_ping=True, hide_parameters=True
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    login = {
        "host": settings.bravo_host,
        "port": settings.bravo_port,
        "database": settings.bravo_database,
        "encrypt": settings.bravo_encrypt,
    }
    bravo = SqlServerBravo(
        read=Login(
            user=settings.bravo_read_user,
            password=settings.bravo_read_password.get_secret_value(),
            **login,  # type: ignore[arg-type]
        ),
        write=Login(
            user=settings.bravo_write_user,
            password=settings.bravo_write_password.get_secret_value(),
            **login,  # type: ignore[arg-type]
        ),
    )
    return WritePipeline(
        verifier=verifier,
        switches=SqlSwitches(SqlRuleVersionLookup(sessions), SqlPauses(sessions)),
        ledger=SqlLedger(sessions),
        directory=bravo,
        rights=bravo,
        documents=bravo,
        engine=bravo,
        writer=bravo,
        now=lambda: datetime.now(UTC),
        tenant_id=settings.tenant_id,
    ), bravo


def main() -> int:
    settings = get_settings()
    try:
        pipeline, bravo = build(settings)
    except SettingsError as refused:
        print(f"dw-bravo-gateway: not starting: {refused}", file=sys.stderr)
        return 2
    app = create_app(
        pipeline,
        fingerprints=bravo,
        orders=bravo,
        directory=bravo,
        environment=settings.environment,
        max_request_bytes=settings.max_request_bytes,
        docs=not settings.is_deployed,
    )
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
