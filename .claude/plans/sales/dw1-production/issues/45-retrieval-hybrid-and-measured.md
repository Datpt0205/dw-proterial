# 45 — Retrieval made hybrid, upgraded and measured (the Qdrant review's findings)

Status: ready-for-agent (before 43 parts 2–3, which retrieve examples)
Blocked by: none
Category: enhancement

## Why

`docs/research/2026-11-17-qdrant-review.md`. Its security finding (a delete
tombstoned another tenant's document) is fixed (`3fbb0db6`). The rest:

## Shape

- **Hybrid search**: bge-m3 dense plus Qdrant's own BM25 text index on the
  chunk text, fused with RRF in one Query API call (prefetch + fusion), under
  the same trusted filter the gateway builds; PO numbers and item codes are
  exact tokens that dense search alone misses. The BM25 statistics are
  scoped so another tenant's documents never shape a tenant's ranking.
- **Upgrade Qdrant** from v1.13.4 to the current release (it carries a REST
  auth-bypass fix) and the client with it, as a fresh instance rebuilt from
  Postgres (a snapshot restores only into the same or next minor); name
  collections by embedding model and switch them with an alias; `is_tenant`
  on the tenant payload index.
- **Latency on CPU, measured**: query embedding with its own short timeout,
  one HTTP client reused, an LRU cache keyed by tenant and workspace; the
  reranker off the mail path (examples need none), and with a timeout that
  falls back fast on the knowledge path; p95 recorded.
- **An eval that can fail**: recall@k and nDCG per labelled set, documents
  counted once, a latency p95, wired into CI's smoke with a floor.
- **Operations**: Qdrant's volume on the Linux VM's own disk, never a
  Windows share or WSL mount; the rebuild from Postgres timed; bge-m3 and the
  reranker in one llama.cpp image replacing Ollama (bge-m3 under llama.cpp
  measured first).
- **Record** the memory ranker as the one searcher outside the gateway
  (SQL picks its candidates) in `CLAUDE.md`.

## Acceptance

1. A search for an exact PO number or item code finds the chunk that holds
   it, where dense search alone ranked it out of the top k (a test).
2. The eval fails when retrieval is broken (demonstrated).
3. Cross-tenant and cross-workspace tests stay green on the new Qdrant.
4. Query p95 on CPU measured and recorded.
