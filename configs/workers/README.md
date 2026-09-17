# Workers

One file per deployable Digital Worker: which graph version it runs, which
prompt bundle, toolset, policy and memory policy it is pinned to, which model
profile it defaults to, and its autonomy level. A run records every one of those
versions, so a result can be traced back to the exact artifacts that produced it.

Empty because a worker is a property of a bounded context, not of the platform.
A process loads only the workers it hosts — `configs/` is shared, and loading a
file whose graph lives in another process would fail fast for the wrong reason.
