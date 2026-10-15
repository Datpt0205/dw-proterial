# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# The reader sandbox (Sales ticket 25, ADR 0010-document-intake-at-real-size-and-format decisions 2 and 6). Every
# customer attachment the API or the worker needs read is read here, by a
# one-use process under `ulimit`, a wall clock and a capped answer, in a
# container with no network at all (`infra/compose/docker-compose.yml`).
#
# It holds no credential, no database driver configuration and no client of
# any store: a parser a hostile file breaks finds a scratch directory and the
# readers' code. The image carries `dw_sales` whole (the readers, its domain
# and, transitively, its dependency tree, none of it reachable without a
# network); slimming it is a measured follow-up (ticket 25, Comments).
#
# Ticket 27's tools are here too: LibreOffice converts a legacy .xls/.doc, and
# Tesseract with Vietnamese reads a scanned page, both inside the same
# containment, both started by the reading process itself.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.31 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/docgen/pyproject.toml apps/docgen/pyproject.toml
COPY apps/reader/pyproject.toml apps/reader/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/python/dw_kernel/pyproject.toml packages/python/dw_kernel/pyproject.toml
COPY packages/python/dw_platform/pyproject.toml packages/python/dw_platform/pyproject.toml
COPY packages/python/dw_agent_runtime/pyproject.toml packages/python/dw_agent_runtime/pyproject.toml
COPY packages/python/dw_knowledge/pyproject.toml packages/python/dw_knowledge/pyproject.toml
COPY packages/python/dw_memory/pyproject.toml packages/python/dw_memory/pyproject.toml
COPY packages/python/dw_connectors/pyproject.toml packages/python/dw_connectors/pyproject.toml
COPY packages/python/dw_observability/pyproject.toml packages/python/dw_observability/pyproject.toml
COPY packages/python/dw_evals/pyproject.toml packages/python/dw_evals/pyproject.toml
COPY packages/python/dw_sales/pyproject.toml packages/python/dw_sales/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev --package dw-reader

# The sources dw-reader installs: its own, the containment it borrows from
# docgen, and dw_sales with the workspace packages dw_sales depends on.
COPY packages/python/dw_kernel packages/python/dw_kernel
COPY packages/python/dw_platform packages/python/dw_platform
COPY packages/python/dw_agent_runtime packages/python/dw_agent_runtime
COPY packages/python/dw_observability packages/python/dw_observability
COPY packages/python/dw_sales packages/python/dw_sales
COPY apps/docgen apps/docgen
COPY apps/reader apps/reader
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package dw-reader

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime

# Security updates from the base image's distribution (as docgen's image).
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

# Ticket 27, the tools a reading process starts (no JRE: --no-install-recommends):
# libreoffice-calc-nogui:   a legacy .xls converted to .xlsx, no X11;
# libreoffice-writer-nogui: a legacy .doc converted to PDF;
# tesseract-ocr, -vie:      a scanned page read as words with boxes, Vietnamese
#                           and English (the -eng data comes with tesseract-ocr);
# poppler-utils:            pdftoppm, a scanned PDF page rasterised for Tesseract;
# fonts-*:                  metric-compatible with the Office fonts, Vietnamese
#                           diacritics covered, for a .doc rendered to PDF.
# Versions are the distribution's; each derived file records the converter's
# own version (`soffice --version`, `tesseract --version`) beside its hash.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libreoffice-calc-nogui \
        libreoffice-writer-nogui \
        tesseract-ocr \
        tesseract-ocr-vie \
        poppler-utils \
        fonts-liberation \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 dw && useradd --uid 1001 --gid dw --no-create-home dw \
    # The socket's directory. A named volume mounted here starts as a copy of
    # it, owned by the one uid the api, the worker and this service share.
    && mkdir -p /run/dw-reader && chown dw:dw /run/dw-reader && chmod 0750 /run/dw-reader

WORKDIR /app
# Owned by root: a reading process cannot rewrite the readers it runs.
COPY --from=builder --chown=root:root /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DW_READER_ROOT=/work \
    DW_READER_SOCKET_PATH=/run/dw-reader/reader.sock

USER dw

# Over the socket: the container has no network to check through.
HEALTHCHECK --interval=15s --timeout=10s --start-period=60s --retries=5 \
    CMD ["python", "-m", "dw_reader.health"]

CMD ["python", "-m", "dw_reader"]
