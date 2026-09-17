# Workers

One file per deployable Digital Worker: which graph version it runs, which
prompt bundle, toolset, policy and memory policy it is pinned to, which model
profile it defaults to, and its autonomy level.

Every run writes those versions onto its own row in `platform.worker_runs`, so
a result traces back to the exact artifacts that produced it with a query, not
with a guess. They are on the row rather than only in the trace on purpose: a
trace is sampled and expires, and provenance that only a sampled span can answer
is not provenance. `release_manifest_ref` does not substitute — it is a text
reference with no table behind it.

`autonomy_level` is declared and, as of today, read by nothing: approval is
decided per tool, so a worker at A4 pauses exactly as often as one at A0. Set it
truthfully anyway; the value is what the approval policy will read when it
learns to.

Empty because a worker is a property of a bounded context, not of the platform.
A process loads only the workers it hosts — `configs/` is shared, and loading a
file whose graph lives in another process would fail fast for the wrong reason.
