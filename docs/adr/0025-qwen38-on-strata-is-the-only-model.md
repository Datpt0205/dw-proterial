---
status: Accepted
date: 2026-11-10
accepted: 2026-11-10 (Đạt: "chỉ dùng model qwen3.8")
supersedes: the 2026-10-18 choice of Qwen3.5-9B on Ollama for the plant's host
source:
    - ../../configs/models/onprem.yaml
    - ../../.claude/plans/ops-hardening.md
    - ../../.claude/plans/sales/dw1-production/issues/01-model-qwen38-on-strata.md
---

# Qwen3.8-Flash-Next on Strata is the only model on Proterial's host

## Context

On 10-18, DW1 and DW2 were set to run Qwen3.5-9B on Ollama on the plant's
host. The host's GPU is an RTX PRO 4000 Blackwell (24 GB). On 10-26,
Qwen3.8-Flash-Next (IQ3_XXS) ran on Strata, on an RTX 3090 (24 GB), over six
DW1 golden sets. It passed every bar, and it beat the 9B model: PRV-code
hints 0.978 vs 0.711, mail intent 1.0 vs 0.898. It made no dangerous error,
and its p50 was 3.3–19.8 s. Q2_0 held the same bars in about half the time.

## Decision

1. One model serves every model step of both DWs: Qwen3.8-Flash-Next,
   served by Strata on the host. No second model is kept as a fallback.
   When the model is down, a step degrades to a person, as
   `configs/models/onprem.yaml` already says.
2. The routing profile stays the one place that names it. A step never
   names a model.
3. Nothing ships until four things are done:
   - Strata is packaged for an offline install;
   - its licence is checked for on-premises commercial use;
   - DW2's, the assistant's and the security sets are measured on it;
   - the whole suite is measured on the RTX PRO 4000 itself.

## Consequences

- Strata replaces Ollama in the on-prem compose, the offline bundle, and
  the warm script.
- The 9B bars and attestations stay in history. Every step is attested
  again on the new model before UAT.
- No smaller model is kept as a fallback, so an outage of Strata means
  work by hand, not worse answers.
