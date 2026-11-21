# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# The Bravo gateway (ADR 0027, sales ticket 63): the one process that holds a
# Bravo login and a SQL Server driver. Typed commands in over DW's internal
# network, the PIC's own save out to Bravo's SQL Server.
#
# The driver is mssql-python, chosen by measuring it in this base image
# against SQL Server 2017 (ticket 63, Comments). Its ODBC driver ships in the
# wheel and needs three libraries from the distribution: libltdl7 (the ODBC
# loader), libkrb5-3 and libgssapi-krb5-2. It loads the distribution's
# OpenSSL 3, which the security updates below keep current.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/bravo-gateway/pyproject.toml apps/bravo-gateway/pyproject.toml
COPY apps/docgen/pyproject.toml apps/docgen/pyproject.toml
COPY apps/reader/pyproject.toml apps/reader/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/python/dw_kernel/pyproject.toml packages/python/dw_kernel/pyproject.toml
COPY packages/python/dw_platform/pyproject.toml packages/python/dw_platform/pyproject.toml
COPY packages/python/dw_agent_runtime/pyproject.toml packages/python/dw_agent_runtime/pyproject.toml
COPY packages/python/dw_knowledge/pyproject.toml packages/python/dw_knowledge/pyproject.toml
COPY packages/python/dw_memory/pyproject.toml packages/python/dw_memory/pyproject.toml
COPY packages/python/dw_connectors/pyproject.toml packages/python/dw_connectors/pyproject.toml
COPY packages/python/dw_bravo/pyproject.toml packages/python/dw_bravo/pyproject.toml
COPY packages/python/dw_observability/pyproject.toml packages/python/dw_observability/pyproject.toml
COPY packages/python/dw_evals/pyproject.toml packages/python/dw_evals/pyproject.toml
COPY packages/python/dw_purchasing/pyproject.toml packages/python/dw_purchasing/pyproject.toml
COPY packages/python/dw_sales/pyproject.toml packages/python/dw_sales/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev --package dw-bravo-gateway

# The sources dw-bravo-gateway installs: its own, Bravo's rule runner and
# contract, and the platform packages its PostgreSQL adapters use.
COPY packages/python/dw_kernel packages/python/dw_kernel
COPY packages/python/dw_platform packages/python/dw_platform
COPY packages/python/dw_bravo packages/python/dw_bravo
COPY apps/bravo-gateway apps/bravo-gateway
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package dw-bravo-gateway

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime

RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends libltdl7 libkrb5-3 libgssapi-krb5-2 \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 dw && useradd --uid 1001 --gid dw --no-create-home dw

WORKDIR /app
# Owned by root: the process cannot rewrite the code that holds the logins.
COPY --from=builder --chown=root:root /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER dw
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"]

CMD ["python", "-m", "dw_bravo_gateway"]
