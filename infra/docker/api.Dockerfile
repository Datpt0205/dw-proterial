# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Stage 1 â€” builder: resolve the uv workspace and install only dw-api deps
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder
# uv binary from the pinned distroless release image
COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /uvx /usr/local/bin/

# Bytecode precompilation can time out on constrained/busy hosts (uv 60s/file
# limit on large files like protobuf). Disabled for build reliability; Python
# compiles .pyc lazily at runtime with negligible impact.
ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Venv must be created at its final runtime path (/app/.venv) â€” entry-point
# scripts embed absolute shebangs, so building elsewhere breaks them.
WORKDIR /app

# Dependency layers first for cache efficiency
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/python/dw_kernel/pyproject.toml packages/python/dw_kernel/pyproject.toml
COPY packages/python/dw_platform/pyproject.toml packages/python/dw_platform/pyproject.toml
COPY packages/python/dw_agent_runtime/pyproject.toml packages/python/dw_agent_runtime/pyproject.toml
COPY packages/python/dw_knowledge/pyproject.toml packages/python/dw_knowledge/pyproject.toml
COPY packages/python/dw_memory/pyproject.toml packages/python/dw_memory/pyproject.toml
COPY packages/python/dw_connectors/pyproject.toml packages/python/dw_connectors/pyproject.toml
COPY packages/python/dw_observability/pyproject.toml packages/python/dw_observability/pyproject.toml
COPY packages/python/dw_evals/pyproject.toml packages/python/dw_evals/pyproject.toml
COPY packages/python/dw_sales_crm/pyproject.toml packages/python/dw_sales_crm/pyproject.toml
COPY packages/python/dw_sales_intel/pyproject.toml packages/python/dw_sales_intel/pyproject.toml
COPY packages/python/dw_lead_scoring/pyproject.toml packages/python/dw_lead_scoring/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev --package dw-api

# Now copy sources and install workspace members
COPY packages/python packages/python
COPY apps/api apps/api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package dw-api

# ---------------------------------------------------------------------------
# Stage 2 â€” runtime: slim, non-root
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --gid 1001 dw && useradd --uid 1001 --gid dw --create-home dw

WORKDIR /app
COPY --from=builder --chown=dw:dw /app/.venv /app/.venv
# Migration entrypoint assets (alembic config + versions)
COPY --chown=dw:dw db/alembic.ini /app/db/alembic.ini
COPY --chown=dw:dw db/migrations /app/db/migrations
# Versioned runtime artifacts the composition root loads from DW_REPO_ROOT
COPY --chown=dw:dw configs /app/configs
COPY --chown=dw:dw evals/fixtures /app/evals/fixtures
COPY --chown=dw:dw contracts/release /app/contracts/release
# Demo fixtures for the dev-only sample-data endpoints
COPY --chown=dw:dw db/fixtures /app/db/fixtures
# The SugarCRM importer runs from this image as a one-off command; it needs
# the package, and `scripts` importable as one, not just the entrypoint file.
COPY --chown=dw:dw scripts/__init__.py /app/scripts/__init__.py
COPY --chown=dw:dw scripts/sugar_migration /app/scripts/sugar_migration
# The importer's cache and watermark live on a named volume mounted here.
# Docker seeds a fresh volume from whatever the image has at that path, so the
# directory has to exist and belong to `dw` before the mount: otherwise the
# volume arrives owned by root and the non-root process cannot write its own
# state, which surfaces only at runtime as a permission error.
RUN mkdir -p /app/var/sugar/cache /app/var/sugar/state && chown -R dw:dw /app/var

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DW_REPO_ROOT=/app

USER dw
EXPOSE 8000

# 90s, not the 20s measured on a developer's machine. On a CI runner that has
# just built four images and is still loading two embedding models, a start
# that is merely slow was being marked unhealthy at ~95s - and compose then
# refuses to start anything that depends on it, so the smoke test failed on
# the clock rather than on the application.
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).status == 200 else 1)"]

CMD ["uvicorn", "dw_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
