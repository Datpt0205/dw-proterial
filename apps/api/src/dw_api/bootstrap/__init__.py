"""Composition root for the API process.

Split by responsibility rather than kept as one long procedure:

* ``paths``      — where versioned artifacts live on disk
* ``telemetry``  — tracing/metrics exporter
* ``identity``   — token verification
* ``storage``    — object storage clients and buckets
* ``knowledge``  — embeddings, reranking, vector index
* ``models``     — model provider adapters and the chat-model factory
* ``runtime``    — registries, gateway, tool executor, workflow runner
* ``container``  — what is handed to routes (``ApiContainer``) and to a
                   bounded context (``RuntimeSeam``)
* ``wiring``     — ``build_container``, the assembly order itself
"""

from __future__ import annotations

from dw_api.bootstrap.container import ApiContainer, RuntimeSeam
from dw_api.bootstrap.paths import REPO_ROOT, release_manifest_ref
from dw_api.bootstrap.wiring import build_container

__all__ = [
    "REPO_ROOT",
    "ApiContainer",
    "RuntimeSeam",
    "build_container",
    "release_manifest_ref",
]
