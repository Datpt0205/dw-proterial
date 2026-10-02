# 10 — Move the Sales decision onto the runtime

Status: needs-triage
Blocked by: 09

## What

Replace the context-recorded decision (spec decision 5) with a versioned
graph that pauses on `interrupt` into the platform approvals inbox and
resumes, so approval, autonomy and audit come from the runtime.
