# Qdrant review: retrieval for knowledge and for corrected cases as examples

Research note, 2026-11-17. This note does not record a decision. Section 4 lists
the decisions it asks for. It is grounded in `dw_knowledge`, `dw_memory`,
dw_sales ADR 0015 (decisions 5-7), ticket 43 and
`docs/research/2026-11-16-less-human-review.md`. "Unverified" marks anything I
did not run or could not confirm in a primary source.

**Short answer.** The tenant fence is in good shape, with one exception: delete
and tombstone ignore the tenant (F1). Retrieval is dense-only, on a Qdrant two
years behind the current release, and nothing has measured its CPU latency. For
ticket 43 you need hybrid search, a newer Qdrant, and an examples index whose
points carry ids rather than text. You do not need a new store.

## 1. Findings

What already holds and should stay as it is:
- Search cannot run without a `TrustedSearchFilter` built from the
  `AccessContext` (`gateway.py:161-172`, `qdrant_index.py:235-311`).
- `SearchQuery` has no tenant fields.
- Narrowing keys are whitelisted (`contracts.py:81-98`), and trusted payload keys
  win any collision (`qdrant_index.py:145-167`).
- `tenant_id` is indexed with `is_tenant`.
- Tombstoned points are excluded from search.
- Offboarding purges both collections.
- Changing the vector width refuses rather than recreating the collection.
- Reindexing builds a new collection.
- Real-Qdrant tests cover cross-tenant, cross-workspace, domain, clearance and
  ACL (`tests/integration/test_qdrant_tenant_filter.py`).

| # | Finding | Where | Severity | Fix |
|---|---|---|---|---|
| F1 | **Soft delete tombstones points by document id alone, even when SQL touched no row.** RLS denies the UPDATE: `knowledge_global_read_documents` is SELECT-only (baseline SQL:767). Qdrant is then tombstoned anyway. Any `knowledge.write` holder can hide a `scope=global` document from every tenant. Every tenant can list global document ids, and the ids are deterministic (`identity.py:392-394`). Inside one tenant, RLS is tenant-only (SQL:773) and the UPDATE has no workspace clause, so a document in another workspace can be deleted by anyone who knows its id. That id is a uuid5 of the workspace and the title. No test covers this. | `gateway.py:552-575`; `qdrant_index.py:178-233` | **High** if any global document exists, otherwise Medium | Add the workspace-visible condition to the UPDATE, with `RETURNING id`, and tombstone only the returned ids. Add `tenant_id` (and `workspace_id`) to `_document_filter`. Add negative tests for both directions. |
| F2 | **Search is dense-only.** PO numbers, item codes and colour codes are exact tokens, and dense vectors match them poorly. bge-m3 can also emit sparse lexical weights, but only through FlagEmbedding (`BGEM3FlagModel`); Ollama and llama.cpp serve dense only ([model card](https://huggingface.co/BAAI/bge-m3)). | `qdrant_index.py:91-104, 298-311` | Medium | Hybrid search: dense plus a lexical prefetch, fused with RRF ([hybrid queries](https://qdrant.tech/documentation/concepts/hybrid-queries/)). See section 2. |
| F3 | **Qdrant v1.13.4 and `qdrant-client <1.15` are pinned.** The current release is v1.20.1 (2026-11-13). Since 1.13 Qdrant has added RRF `k` (1.16), ACORN (1.16), tiered multitenancy (1.16), weighted RRF (1.17), per-tenant IDF statistics (1.19), BM25 scoring on the full-text index (1.20) and a `code` tokenizer (1.20). It also fixed a REST auth bypass in 1.18.2 ([releases](https://github.com/qdrant/qdrant/releases)). | `docker-compose.yml:117`; `dw_knowledge/pyproject.toml:12`; `dw_memory/pyproject.toml:14` | Medium | Upgrade to 1.20.x as a **fresh instance plus reindex from Postgres**. A snapshot restores only into the same or the next minor version ([snapshots](https://qdrant.tech/documentation/snapshots/)), so restoring would mean seven hops. |
| F4 | **Rerank latency on CPU has never been measured, and a failure costs the full timeout.** A search over-fetches `top_k × 4` (32) chunks of up to 1,200 characters each. The reranker is the same XLM-R-large size as bge-m3 (0.6B; its card truncates at 512 tokens, [card](https://huggingface.co/BAAI/bge-reranker-v2-m3)). My estimate is seconds to tens of seconds per query on the plant VM's CPU (**unverified**). A slow reranker is only abandoned after `DW_API_RERANK_TIMEOUT_SECONDS` (10 s), on every query. | `gateway.py:211, 582`; `cohere_rerank.py:133`; `docker-compose.yml:362` | Medium | Measure first. Then cap at 16-20 candidates truncated to 512 tokens, add a circuit breaker that stops calling for a while after N timeouts, and keep rerank off a mail's path unless it fits that step's budget. |
| F5 | **Query embedding has no separate deadline, no cache, and opens a new client per call.** The route's 120 s timeout applies to a one-line query too. Each call opens a new `httpx.AsyncClient`. | `onprem.yaml:92`; `openai_embedding.py:285-289`; `cohere_rerank.py:154-163` | Medium | Add a query deadline of about 3-5 s and one shared client per process. Cache query vectors in Valkey under `tenant:workspace:model:sha256(text)` with a TTL. The cache is never the source of truth. |
| F6 | **The retrieval eval cannot fail.** `passed` only means "has cases" (`retrieval_eval.py:43-44`). Several chunks of one document fill the precision denominator (`:53-57`). It reports no nDCG and no latency, has no labelled set per tenant, and only unit tests call it. | `retrieval_eval.py` | Medium | See section 2, "Evaluation". |
| F7 | **Indexing is not tuned for tenants.** `scope` is filtered in a `should` but has no index. Global points are OR-ed into every query, so a per-tenant graph (`m: 0, payload_m: 16`, [multitenancy](https://qdrant.tech/documentation/guides/multiple-partitions/)) cannot serve them. HNSW settings are never set, and nothing reconciles them on an existing collection. | `qdrant_index.py:27-39, 91-104, 293-304` | Low now; Medium at SaaS scale | Index `scope`. Put global documents under a pseudo-tenant `global`, fetched by their own prefetch. Use `payload_m`/`m: 0` once a tenant passes about 20k points. |
| F8 | **The memory collection is a second searcher outside the gateway**, with no `is_tenant` and no quantization. It is safe because SQL picks the candidates (`HasIdCondition`). Still, `CLAUDE.md` says filters are injected only in the knowledge gateway. | `dw_memory/adapters/qdrant_ranker.py:73-93, 144-187` | Low | Record the exception: Qdrant only orders ids that SQL chose. Add `is_tenant`. |
| F9 | **Chunking is by character count and knows nothing of tables, mails or Japanese.** 1,200 characters of Japanese is about 2-3× the tokens of Vietnamese, so the reranker's 512-token cut drops the tail. Headings such as 第1条 are not detected. Table rows are split away from their header. | `chunking.py:22-25, 81-100` | Low (knowledge is not on DW1's path today) | Use a token budget from the bge-m3 tokenizer. Make one chunk per table row group, with the header repeated. Make one chunk per mail message, with quoted history stripped. |
| F10 | **A collection's model is identified only by its width.** Switching models means editing an environment variable and restarting. | `embedding_factory.py:3-8`; `qdrant_index.py:59-70`; `scripts/knowledge_reindex.py:18` | Low | Name collections `<name>__<model>__<index_version>` and serve them behind an alias. Switch by moving the alias. Check the model name at start-up. |
| F11 | **There is no Qdrant backup or restore runbook.** Recovery time is the time to reindex on CPU, which has not been measured. | `infra/onprem/README.md` | Low | The backup is the reindex from Postgres. Measure it and write the recovery time down. Add a nightly collection snapshot only if the reindex is too slow. |
| F12 | **The rerank score scale on llama.cpp is unknown** (**unverified**). Raw logits would be clamped to [0,1], and `min_relevance` would then mean different things on each path. | `gateway.py:604-619` | Low | Measure. Apply a sigmoid in the adapter if the scores are raw ([card](https://huggingface.co/BAAI/bge-reranker-v2-m3): `normalize=True`). |

## 2. Recommended target design

- **One Qdrant 1.20.x**, with three collections behind aliases: `dw_knowledge`,
  `dw_memory` and `dw_examples`. Each has:
  - a named `dense` vector (bge-m3, 1024, cosine);
  - INT8 scalar quantization held in RAM, which keeps loss under about 1%
    ([quantization](https://qdrant.tech/documentation/guides/quantization/));
  - original vectors on disk, with rescoring on.

  Binary quantization stays out: Qdrant reports it holding up only for some
  models, and recall drops at low dimension.
- **Lexical side, using Qdrant itself.** Put a full-text index on the searchable
  text with BM25 scoring (1.20) and the `multilingual` tokenizer (Japanese via
  vaporetto; Vietnamese is space-delimited) ([indexing](https://qdrant.tech/documentation/concepts/indexing/)).
  Turn on phrase matching so `PO-2026-001` matches as a sequence. This adds no
  model server. The alternative is bge-m3's learned sparse weights, which need a
  FlagEmbedding (PyTorch) service on CPU (decision 1).
- **One query** of two prefetches, fused with RRF:
  - dense, limit about 40;
  - BM25, limit about 40.

  Both run under the **same** trusted filter, built only in the gateway.
  Lexical statistics are scoped to the tenant's own points through the `idf`
  parameter (1.19). Otherwise every other tenant's corpus shapes this tenant's
  ranking. Rerank runs only where measured to fit.
- **Tenancy.**
  - `tenant_id` stays `is_tenant`.
  - Global documents become their own prefetch, not an OR.
  - Delete and tombstone also filter on the tenant (F1).
  - One collection with payload partitioning, as Qdrant recommends over a
    collection per tenant ([multitenancy](https://qdrant.tech/documentation/guides/multiple-partitions/)).
- **Serving on the plant.** Strata serves no embeddings. One pinned llama.cpp
  image serves bge-m3 dense (`--embedding`) and the reranker, replacing Ollama,
  which no longer serves chat. **Unverified** for a bge-m3 GGUF: check that its
  vectors match FlagEmbedding's (cosine above 0.99 on 100 texts) before
  reindexing.
- **Latency budget for retrieving examples:**
  - embed the input once per mail and reuse it across steps (cached);
  - one Qdrant query, an estimated few ms to tens of ms at hundreds of cases;
  - no rerank.

  Target p95 under 300 ms on the plant VM (**unverified estimate**). Report it
  per step, as ADR 0015 decision 7 asks.
- **Evaluation.** Use a labelled set per tenant and per corpus, taken from real
  queries and the cases a person kept, held out by thread. Measure:
  - recall@k, nDCG@10 and MRR at document level, after de-duplicating
    documents (the BEIR convention, [Thakur et al. 2021](https://arxiv.org/abs/2104.08663));
  - p50 and p95 for embed, search and rerank, each separately.

  Fail the run on a regression against the last accepted figures, inside
  `scripts/run_evals.py`. Run every change of model, chunking or fusion through
  it before switching the alias.
- **Operations.**
  - Reindexing from Postgres is the restore path. Measure its duration.
  - The Qdrant volume sits on the Linux VM's own virtual disk. It never sits on
    a Windows share, the SMB mail-drop or a WSL mount. Qdrant requires POSIX
    block storage and warns that Docker/WSL mounts on Windows lose data
    ([installation](https://qdrant.tech/documentation/installation/)).
  - Give the VM vCPUs with AVX2/AVX-512 exposed (**unverified** under Hyper-V),
    and measure embedding throughput there, not on a dev box.

## 3. What this changes in ticket 43

1. **Corrected cases live in PostgreSQL** under RLS (FORCE, grants, retention),
   as the ticket says. `dw_examples` holds only the vector and the filter fields:
   `tenant_id` (is_tenant), `workspace_id`, `step_id`, `subject_ref` (the
   customer), `created_at` and `case_id`. **It holds no text.**
2. **Retrieval goes through the knowledge gateway.** A new method takes the step,
   the customer and the input text. The tenant and workspace filter come from the
   `AccessContext`. Step and customer come from code: the customer is the case's
   resolved binding, never model output. The method returns ids. The text and
   the right answer are re-read from Postgres under RLS, so a filter regression
   in Qdrant cannot put another tenant's words into a prompt. dw_sales reaches
   the method through a Protocol it declares itself, satisfied at the
   composition root.
3. **Embed the input exactly as the model read it** (the normalised mail or PO
   text, truncated). Never embed the model's answer or the correction.
   Similarity between inputs is what made retrieved examples beat random ones
   ([Liu et al.](https://arxiv.org/abs/2101.06804)). BM25 catches the codes.
4. **Choosing the examples.**
   - k = 3-5, filled from the same customer first, then from the rest of the tenant.
   - At most one per thread, or MMR, for diversity (the Query API has `mmr`;
     its parameter's direction differs between sources and is **unverified**).
5. **Reproducible replays.** A run stamps `examples_as_of`, and the search
   filters `created_at ≤` that stamp. This makes it the "example-bank snapshot"
   in the readiness key.
6. **An honest eval.** A held-out case never retrieves itself, its thread or its
   PO (`must_not`). Without this, acceptance 2 measures leakage.
7. **Examples stay untrusted.**
   - Each example enters through `PromptRegistry` as an escaped
     `<input name=...>` block (ADR 0010).
   - Only cases whose right answer passed the step's code checks become examples.
   - Length is capped.
   - The eval dataset gains a case with an injection planted inside an example.
   - Examples change wording, never a tool, scope, number or move (ADR 0015
     decision 6).
8. **Write and delete paths.**
   - The worker writes the vector after commit, best-effort, like the memory
     ranker: a missing point only means the case is not retrieved.
   - Retention, supersession and offboarding delete points, and raise on failure.
   - Add `dw_examples` to the offboarding purge, and add a negative test for
     acceptance 1 against real Qdrant.

## 4. Decisions for Đạt

1. **Lexical search:** Qdrant's own BM25 full-text index (recommended: no new
   service), or bge-m3 sparse weights through a FlagEmbedding service on CPU?
2. **Upgrade** Qdrant to 1.20.x as a fresh instance with a reindex, before
   ticket 43 starts?
3. **Embedding and rerank serving:** both on CPU on the plant VM through
   llama.cpp, dropping Ollama? Or a share of the GPU beside Strata if CPU
   measures too slow? Both need a measurement on the plant VM.
4. **Rerank off the mail path** unless measured within the step's p95 budget?
5. **Where the examples index lives:** in `dw_knowledge`, generic over
   `step_id`, so DW2 reuses it (recommended), with each context owning its
   corrections table?
6. **ADR 0015 decision 7, "the tenant's own collection":** read it as "the
   tenant's own partition" (`is_tenant`), not a collection per tenant?
7. **Global (cross-tenant) documents:** keep them at all on DW deployments?
   Without them, F1's worst case disappears and per-tenant graphs become simple.
