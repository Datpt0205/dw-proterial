# 01 — The model is Qwen3.8-Flash-Next on Strata, attested on every set

Status: needs-info (Strata's offline package and licence; the plant's GPU)
Blocked by: Giang's Strata build for offline use; the RTX PRO 4000 on site
Category: enhancement

## Why

Đạt, 11-10: Qwen3.8 only, no Qwen3.5-9B (`docs/adr/0025`). Measured 10-26
on six DW1 sets on an RTX 3090: every bar passed. Not measured: DW2's sets,
the Q&A sets, the security cases, the plant's GPU.

## Shape

- `configs/models/onprem.yaml`: every route to the Strata model under a new
  `routing_policy_version`; thinking stays off; still no fallback route.
- `scripts/warm_model.py` and `model-warm` warm Strata, not Ollama.
- The on-prem compose runs Strata from a saved image; the offline bundle
  carries it with the weights.

## Acceptance

1. Every DW1 and DW2 golden set, the assistant sets and the security cases
   pass their bars through the profile on the RTX PRO 4000; the results go
   into the plan file.
2. The streamed chat (`released`) still holds every word until it passes.
3. With Strata down, every step degrades to a person, asserted by a test.
4. The licence allows on-premises commercial use, written down.

## Comments
