# 45 — Retrieval made hybrid, upgraded and measured (the Qdrant review's findings)

Status: done (2026-11-15) — llama.cpp in place of Ollama left open, see "Left"
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

## Done (2026-11-15)

- **Upgrade.** Qdrant `v1.13.4` → `v1.20.1` (`infra/compose/docker-compose.yml`),
  `qdrant-client` `<1.15` → `>=1.20,<1.21` (1.20.0) in `dw_knowledge`,
  `dw_memory`, `apps/api`, `apps/worker`, `uv.lock`. Measured first: the
  existing knowledge and memory integration tests (46) green on the new server
  before any code changed. Only the `qdrant` container was recreated, on an
  emptied `dw_proterial_qdrant-data` volume (`docker compose ... rm -s -f qdrant`,
  `docker volume rm`, `up -d --wait qdrant`): it held only empty
  `dw_knowledge_test_*` leftovers, and the dev `dw` database has 0 knowledge
  documents, so there was nothing to rebuild locally.
- **Hybrid search** (`dw_knowledge/hybrid.py`, `adapters/qdrant_index.py`): one
  Query API call, a dense prefetch and a BM25 prefetch on the full-text index
  of the chunk text (`content`, `scoring: true`), fused by `RrfQuery(k=2)`. The
  whole trusted filter is on both prefetches and on the fusion. No new model
  host: BM25 is Qdrant's own (1.20), not a sparse vector.
  - Tokenizer `word`, not `multilingual`: measured on 1.20.1, `multilingual`
    drops digit-only tokens, so `PO-2026-0457` indexed as `po` alone.
  - k=2 (Qdrant's default) by measurement on the labelled set: nDCG@5 0.76 at
    k=2 against 0.71 at k=10 and k=60.
  - A hit's score is the fused relevance on [0, 1] (RRF over its 2/k maximum),
    so `min_relevance` keeps its scale.
- **BM25 statistics scoped** to what the trusted filter admits (`idf` corpus on
  the BM25 prefetch). Measured: Qdrant computes them shard-wide by default; one
  tenant's score fell 2.95 → 1.76 when another tenant added 80 points, and
  stayed 2.95 with the corpus scoped. An `idf` on the outer query does not
  reach the prefetches (measured), so it sits on the prefetch. The corpus is
  the caller's readable set (own workspace plus global documents it may read,
  its classifications and ACL), never the business narrowing, so a score is a
  function of text the caller could read: it reveals no other tenant's
  document. Residual, measured: Qdrant orders exactly equal scores by where
  points sit, which any write can change; that order carries no text.
- **In-memory index** (`adapters/memory_index.py`) ranks the same way (cosine +
  BM25 over the admitted corpus + the same RRF), so the CI eval measures what
  Qdrant serves.
- **Aliases, `is_tenant`.** `QDRANT_COLLECTION` is an alias over
  `<alias>__<model>__<build>`; `ensure_ready` creates `__1` and the alias, and
  refuses a collection built by another model or width. `EmbeddingPort` gained
  `model`. The gateway's search now runs `ensure_ready` once per process, so the
  API checks the model too. `scope` got a keyword index. The memory ranker's
  `tenant_id` index is `is_tenant` (`dw_memory/adapters/qdrant_ranker.py`).
  Rebuild from Postgres: `scripts/knowledge_reindex.py` fills a new build and
  moves the alias atomically, prints the old one, and `DW_REINDEX_SERVE=<name>`
  moves it back.
- **Latency.** One reused `httpx.AsyncClient` in the embedding and rerank
  adapters; the query embedding has its own 5 s deadline in the gateway; an
  LRU of 1,024 query vectors keyed by tenant, workspace and text. The reranker
  keeps its timeout (`DW_API_RERANK_TIMEOUT_SECONDS`, 10 s) and falls back to
  the fused order.
- **p95 on CPU, measured** (this laptop, Qdrant 1.20.1 in Docker Desktop, the
  local stack's **hash** embedder; 4,034 points across two tenants, 300
  searches, top 32): hybrid search p50 8.4 ms, **p95 10.7 ms**; dense alone
  p95 7.7 ms; hash embedding 0.1 ms. The labelled set on Qdrant: p95 12.4 ms.
  bge-m3 query embedding and rerank on CPU are not in these numbers (no bge-m3
  or reranker on this machine).
- **Eval that can fail** (`dw_knowledge/retrieval_eval.py`,
  `dw_evals` graders `knowledge.retrieval_quality` and
  `knowledge.ranking_isolated`, `evals/datasets/platform@1.3.0.json`, fixture
  `evals/fixtures/cases/pf_retrieval.json`, floors in `evals/expected/`):
  recall@5, nDCG@5, MRR over documents counted once, p95; floor recall 0.9,
  nDCG 0.65, p95 100 ms. Measured: in memory recall 1.0 / nDCG 0.76; on
  Qdrant recall 1.0 / nDCG 0.795. Demonstrated red: lexical leg dropped →
  recall 0.70, nDCG 0.536 (in memory and on Qdrant); BM25 statistics over every
  tenant → the isolation case fails. Dropping the dense leg instead stays
  green: with the hash embedder the dense leg carries no meaning, so only a
  live run with bge-m3 can gate it.
- **Acceptance.** 1: `test_qdrant_hybrid.py::test_an_exact_po_number_is_found_where_dense_search_alone_misses_it`.
  2: above. 3: knowledge + memory integration green on 1.20.1 after the change.
  4: above.
- `CLAUDE.md` records the memory ranker as the one searcher outside the
  gateway; `infra/onprem/README.md` the alias and the volume's placement.

## Decisions taken

- Trivy 0.74.0 on `qdrant/qdrant:v1.20.1`: 2 HIGH, both Debian `zlib1g`
  (CVE-2026-76844, CVE-2026-85091), fixed in `deb13u1` of the base image and
  not yet in a Qdrant release; Cargo dependencies clean. Accepted: the image is
  on `dw-internal`, and the fix arrives with the next Qdrant patch release.
- Collection names carry the model, not `INDEX_VERSION`: a rebuild is named by
  its UTC stamp, so the same model and chunking can be rebuilt (after an
  upgrade) without colliding.
- The first build is always `__1`: creating an alias that exists silently
  repoints it (measured), so two processes starting together must create the
  same collection, not two.
- A collection made before aliases (the alias's own name) is still served,
  checked by width only; moving it behind an alias is the rebuild's last step.

## Left

- llama.cpp serving bge-m3 and the reranker in place of Ollama: not done
  (needs the bge-m3 GGUF download and its cosine check against FlagEmbedding).
- Rerank latency on CPU and a circuit breaker: unmeasured here (no reranker on
  this machine); the 10 s timeout with fallback stays.
- Global documents as their own prefetch, quantization/HNSW tuning per tenant
  (review F7): not in this ticket.
- The rebuild from Postgres is not timed on real data (the local database has
  no knowledge documents); time it on the plant VM.
- Qdrant metadata calls (create collection, payload index) took 2.4–4.7 s each
  on this Docker Desktop volume, on 1.13.4 and 1.20.1 alike: a first
  `ensure_ready` takes about 40 s here.
