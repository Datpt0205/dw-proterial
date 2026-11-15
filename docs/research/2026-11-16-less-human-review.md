# Less human review: auto-accept with a measured error bound

Research note, 2026-11-16. Not a decision: section 4 lists the decisions it asks
for. Grounded in dw_sales ADRs 0005, 0012-0014, platform ADRs 0025/0026, and
DW1 production tickets 01 and 40-42. Every external claim links to its primary
source. "Unverified" marks what I could not check.

## 1. Is the direction right?

Mostly, yes, and the strongest part is the part people tend to drop. The
literature backs the core pattern: a model reads into a typed schema, and code
checks the result against the source (quotes located, figures re-parsed, legal
moves). Without an outside check, models do not reliably correct themselves
([Huang et al., ICLR 2024](https://arxiv.org/abs/2310.01798)). Picking among
samples without an automatic verifier levels off
([Brown et al., 2024](https://arxiv.org/abs/2407.21787)). The other parts are
sound too: versioned prompts and skills, security evals, one model, and an ERP
write only after a person approves the exact file.

What keeps people in the loop for no gain is the **decision rule**, not the
reading.

- **A passed bar saves no work.** It turns a step on, but the result is still a
  proposal, and a person confirms nearly every one. The bar buys no labour.
- **The bar cannot tell 0.80 from 0.85.** It is one accuracy figure over every
  item, on 33-92 fictional cases. The golden sets hold 60 replies, 34 RFQs and
  92 messages. A 95% interval for 48 of 60 runs from 0.68 to 0.88, so reply
  intent's "fail" (0.796) and a "pass" at 0.85 are about three mails apart and
  statistically the same. A point bar cannot justify auto-accepting anything.

Current practice uses **selective prediction with risk control** instead, and it
decides each item on its own:

> code checks pass AND a score clears a threshold chosen on the tenant's own
> labelled outcomes, so that the error rate *among auto-accepted items* is ≤ α
> with stated confidence → apply automatically; otherwise → a person.

This turns the bar into a dial. The same model and prompt give a share of items
that go straight through, at a guaranteed error rate. A better skill, prompt or
set of examples then shows up as a larger share, not as a code change.

The second gap is in ADR 0014. Letting the agent choose its skill and tools puts
the least-measured behaviour on the critical path: Qwen3.8 called the expected
tool in only half the turns that needed one (ticket 01). Keep skills as content
the tenant edits, but choose the skill with one constrained, scored call.

## 2. Recommended architecture

For every model step, at every tenant:

1. **Read.** The tenant's skill version plus *k* retrieved corrected cases of
   that tenant produce JSON constrained by the step's schema
   (llama.cpp `response_format: json_schema`,
   [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)),
   validated into the Pydantic type. No change from today except the examples.
2. **Verify (code, unchanged).** Spans located, figures re-parsed, schema
   checked, tenant and customer binding, legal moves. If any check fails, the
   item goes to a person, as today.
3. **Score.** One number per item, *s* ∈ [0, 1], from the cheapest signal that
   ranks well on our labels:
   - **(a) Label-token probability from the same call.** No extra call.
     llama.cpp exposes `n_probs` / `top_logprobs`. Whether Strata passes them
     through is *unverified*: one request settles it.
   - **(b) Agreement of 3-5 samples,** used only when (a) falls in a middle
     band. This is a cascade, as in
     [Jung et al., ICLR 2025](https://arxiv.org/abs/2407.18370).
   - **(c) Never the model's stated confidence alone.** Models state it
     overconfidently ([Xiong et al., ICLR 2024](https://arxiv.org/abs/2306.13063)).

   The guarantee in step 4 does **not** need the score to be well calibrated: a
   poor score only lowers the share that goes straight through. That matters on
   a 2-bit model, whose confidence quantization is known to distort
   ([Proskurina et al., NAACL Findings 2024](https://arxiv.org/abs/2405.00632)
   studied 4-bit; 2-bit is untested).
4. **Gate.** An item is auto-accepted when step 2 passes AND *s* ≥ λ̂(step,
   tenant, versions). λ̂ is set by Learn-then-Test, using fixed-sequence testing
   ([Angelopoulos et al.](https://arxiv.org/abs/2110.01052); the same procedure
   as [Trust or Escalate](https://arxiv.org/abs/2407.18370)):
   - Scan λ from strict to loose.
   - Stop at the first λ where the exact (Clopper-Pearson) upper bound on the
     error rate among accepted items, at confidence 1−δ, exceeds α.
   - Result: with probability ≥ 1−δ, the error among auto-accepted items is
     ≤ α, provided new items look like the calibration items (exchangeable).
5. **The risk tier sets what "auto" may do:**
   - **T0, reversible and internal.** Classifying a mail, reading reply or
     thread intents, reading fields into a case, PRV candidates, summaries,
     the morning brief, finding explanations, a draft reply that is not sent,
     a hand-off draft. Auto means applied and shown as done, stamped "read by
     the model, auto-accepted at λ̂, versions …", and undone with one click.
   - **T1, internal but others act on it.** A hand-off actually delivered to
     PC or QA, or a case move that puts work in another person's queue. Auto
     only with a stricter α and an undo; Đạt to decide.
   - **T2, irreversible or external.** Anything sent to a customer, any Bravo
     write, prices, delivery dates, approvals, checker roles, finding
     dispositions. **Always a person**, unchanged (ADR 0026; ADR 0005's "what
     stays human"). The saving here comes upstream: the person approves one
     assembled file whose cells are all traced (ticket 41), with only the
     untraced or low-score cells highlighted, instead of confirming every step
     that built it.
6. **Labels come free.** Every item a person handles gives a pair: what the
   model proposed and what the person kept. That pair is a correct-or-wrong
   label. *Missing today:* `sales.step_outcomes` records what the step did, but
   I found no record of the person's final value per proposal. This is the one
   new piece of data the design needs.
7. **Audit by sampling.** A fixed share (2-5%, tenant config) of auto-accepted
   items is sent to a person who is not told it was accepted. This gives an
   unbiased error rate for the automatic path, and labels for the region that
   would otherwise never get any. AWS's human-review service is built around
   the same two triggers, low confidence and random samples
   ([A2I docs](https://docs.aws.amazon.com/sagemaker/latest/dg/a2i-use-augmented-ai-a2i-human-review-loops.html)).
8. **Recalibrate; drift and kill switch.**
   - A nightly worker lane recomputes λ̂ from the latest labels for each step
     and version.
   - A new model, skill or prompt version, or example-bank snapshot, sets auto
     **off** until enough labels exist for it. That is today's readiness rule,
     with the readiness key widened to cover them.
   - An alarm fires and auto turns off when the audited error's lower bound
     exceeds α. Adaptive conformal inference is the principled online version
     ([Gibbs & Candès, NeurIPS 2021](https://arxiv.org/abs/2106.00170)).
   - The kill switch is the existing per-tenant `model_assist` switch.
9. **Learn without code.**
   - Corrected cases go into a tenant example bank: under RLS, versioned by
     snapshot, contained as untrusted input (ADR 0010). They are retrieved by
     similarity as few-shot examples. This needs an embedding server: Strata
     refuses `/v1/embeddings`, so bge-m3 needs its own.
   - Each week, an offline optimiser (DSPy MIPROv2 or GEPA) runs on the
     tenant's labels and proposes a **skill version**. That version goes
     through the existing rule-version flow (replay, the head approves, never
     the proposer), is recalibrated, and the auto share moves. No deploy.
10. **Shadow first.** Until a step has enough labelled *real* items, step 4 is
    computed and logged but not applied. The confirmations people do today
    become the calibration data. This keeps "HITL until the plant survey" and
    makes it end on evidence.

**How many labels.** The arithmetic below uses exact binomial bounds at δ =
0.05, counting only items accepted by the threshold.

| Target α | Labels needed, no errors allowed | Labels needed, 2 errors allowed |
| --- | --- | --- |
| 5% | 59 | 124 |
| 2% | 149 | 313 |
| 1% | 299 | 628 |

For stable conformal coverage, the standard guide recommends about 1,000 points
([Angelopoulos & Bates, §3.2](https://arxiv.org/abs/2107.07511)).

The guarantee is an average over all items. Japanese reads worst (0.611-0.647),
so calibrate per language or per customer group once a group has enough labels
(group-conditional conformal, same guide, §4.1). Until then that group stays
with a person, which is the right outcome. DW1's mail volume per step is
unknown to me, so how long shadow mode lasts is for Đạt to estimate.

## 3. Methods

| Method | Evidence (primary source, its numbers) | Fit: 2-bit 125B MoE, one 24 GB GPU | Cost | Call |
| --- | --- | --- | --- | --- |
| **Selective prediction with risk control** (Learn-then-Test, conformal risk control, conformal abstention) | Top-5 error held at 2% with 99.9% confidence while classifying about 60% of ImageNet ([Geifman & El-Yaniv 2017](https://arxiv.org/abs/1705.08500)). Bounds the expected loss at ≤ α ([CRC, ICLR 2024](https://arxiv.org/abs/2208.02814)). A Mistral-7B cascade guarantees >80% human agreement at about 80% coverage ([ICLR 2025](https://arxiv.org/abs/2407.18370)). Bounds the hallucination rate using a self-consistency score ([Yadkori et al. 2024](https://arxiv.org/abs/2405.01563), preprint) | Model-agnostic; arithmetic on labels | Labels (already produced by people) and a nightly job | **Adopt** |
| Token-probability score | White-box confidence beats black-box only narrowly (AUROC 0.605 vs 0.522, [Xiong et al.](https://arxiv.org/abs/2306.13063)). Quantization lowers confidence, most on items that were already uncertain ([Proskurina et al.](https://arxiv.org/abs/2405.00632)) | Depends on Strata exposing logprobs (unverified) | No extra call | **Adopt if exposed**; measure its AUROC on our labels |
| Sample agreement / semantic entropy | AUROC 0.790 vs 0.698 for P(True), averaged over 30 task-model pairs, with 10 samples ([Farquhar et al., Nature 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11186750/)). Self-consistency adds 3.9-17.9 points on reasoning ([Wang et al., ICLR 2023](https://arxiv.org/abs/2203.11171)) | Black-box; works on any server | About k× GPU time, so 5-10 s for k = 5 unless Strata runs parallel slots (unmeasured; Ollama refused them for this model) | **Later**, only for the middle band |
| Stated (verbalized) confidence | Overconfident ([Xiong et al.](https://arxiv.org/abs/2306.13063)). Better than token probabilities on large RLHF models, about 50% lower calibration error ([Tian et al., EMNLP 2023](https://arxiv.org/abs/2305.14975)) | Untested on a 2-bit model | None | **No** as the only signal |
| Same-model LLM judge | Self-correction without outside feedback does not help reasoning ([Huang et al.](https://arxiv.org/abs/2310.01798)). Without automatic verifiers, majority vote and reward models level off ([Brown et al.](https://arxiv.org/abs/2407.21787)) | Shares the generator's blind spots | 2× calls | **No**; code verification is our verifier |
| Constrained decoding (JSON schema) | Equal or better than unconstrained: llama.cpp backend GSM8K 80.1 → 82.4%, Last Letters 50.7 → 52.0%, Shuffle Objects tied. llama.cpp's real coverage of hard schemas is low (0.39) ([JSONSchemaBench](https://arxiv.org/html/2501.10868v3)). Strict formats can hurt reasoning ([Tam et al. 2024](https://arxiv.org/abs/2408.02442)) | Our outputs are closed sets and spans; llama.cpp supports `response_format` | Near zero | **Adopt**: keep schemas simple; put a quote or reason field before the label; check that Strata passes it through |
| Similar corrected cases as few-shot | Retrieving similar examples beats random ones: +41.9% ToTTo, +45.5% NQ ([Liu et al.](https://arxiv.org/abs/2101.06804)) | Good; needs an embedding server | Small | **Adopt** once labels exist |
| Prompt optimisation (MIPROv2, GEPA) | MIPRO up to +13% accuracy on Llama-3-8B ([EMNLP 2024](https://arxiv.org/abs/2406.11695)). GEPA more than 10% over MIPROv2, and on average 6% over GRPO with up to 35× fewer rollouts ([ICLR 2026](https://arxiv.org/abs/2507.19457)) | Offline, overnight, on the plant model; output is a skill version to approve | Hundreds to thousands of calls per run (estimate) | **Later**, after about 100 labels per step |
| Fine-tuning / LoRA | QLoRA fine-tunes 65B on one 48 GB GPU ([Dettmers et al.](https://arxiv.org/abs/2305.14314)) | Not feasible for 125B on 24 GB; ADR 0025 allows one model | High | **No** |
| Skills (SKILL.md), chosen by the model | Curated skills raise pass rate from 33.9% to 50.5% across 18 configurations ([SkillsBench 2026](https://arxiv.org/abs/2602.12670), preprint). The benefit is fragile and falls toward the no-skill baseline in realistic retrieval ([Liu et al. 2026](https://arxiv.org/abs/2604.04323), preprint). Selection runs on the `description` alone ([Anthropic](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview), [deepagents](https://docs.langchain.com/oss/python/deepagents/skills)). Anthropic says to build evals first and test with every model you will use ([best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)) | Ticket 01: expected tool called in half the turns that needed one | One more call per turn | **Adopt as content**; choose the skill with one constrained, scored call |
| Risk-tiered oversight | Oversight "commensurate with the risks, level of autonomy and context"; names automation bias; requires override and stop ([EU AI Act Art. 14](https://artificialintelligenceact.eu/article/14/); cited as practice, applicability not checked). Measure and manage functions ([NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework)). In ERP practice, invoices within tolerance post automatically and outside it are blocked for payment ([SAP](https://help.sap.com/saphelp_sfin100/helpdata/en/fc/70b6531de6b64ce10000000a174cb4/content.htm)) | Matches the tiers in section 2 | None | **Adopt** |

**Thin evidence.**

- I found no peer-reviewed figures for straight-through rates in invoice or PO
  automation. Vendor pages describe per-field thresholds and review queues
  without data.
- No study covers calibration of 2-bit GGUF models.
- The skill benchmarks are 2026 preprints.

## 4. What changes

- **ADR 0005.**
  - Decision 3, "a person confirms", becomes "a person confirms unless the
    step's gate (section 2, step 4) passes for its tier".
  - Decision 9 and the 2026-10-23 bar become two figures per step, tenant and
    version set: α, certified on real labelled outcomes, and the share it
    yields. The readiness key adds skill version and example-bank snapshot.
  - The fictional golden sets stay as must-pass regression and security gates.
    They cannot certify auto-acceptance.
- **ADR 0014.**
  - Keep tenant skills and "code guards".
  - Amend decisions 1 and 3: "the agent loads the skill it needs" becomes "one
    constrained call chooses among the tenant's skills, scored and gated like
    any step". Code builds the label set from the served skills, so a new skill
    still needs no code.
  - The open agent loop is used only to fetch tools, measured per skill.
- **Ticket 40.**
  - Record the proposal and the person's final value for each item, and store
    the score with the step outcome.
  - `skill_intents` becomes ready by Learn-then-Test, not by the 0.85 point
    bar.
  - Japanese is calibrated as its own group, or stays with a person.
- **Ticket 41.** The cell trace is the verifier. Add a score per cell. The file
  stays T2: one approval, with untraced or low-score cells highlighted.
- **Ticket 42.** Each family that moves gets the gate and the labels. The table
  of mail kinds becomes the catalogue's label set.
- **New tickets.**
  1. A calibration lane: outcome labels, a nightly λ̂ per step, and audit
     sampling.
  2. A Strata capability check: logprobs, `response_format` json_schema,
     several samples per request, parallel slots.
  3. A tenant example bank with an embedding server.

**Decisions for Đạt**

1. **α per tier.** Suggested: T0 5%, T1 1-2%, T2 never automatic; δ = 0.05.
   These are tenant config, not code.
2. **Which effects are T0 and which are T1.** Above all: an internal hand-off
   to PC or QA, and case moves into another person's queue.
3. **The audit share** (2-5%), and who audits.
4. **Shadow until the plant.** Auto-apply starts only once real labelled items
   reach the counts in section 2, which keeps the 11-04 HITL rule.
5. **Choosing the skill.** One constrained, scored call, or the agent's free
   choice as ADR 0014 now says.

## 5. Sources

Each source is linked inline where it is used. Primary sources only: arXiv,
proceedings and official documentation. Venues as confirmed:

- **ICLR 2024:** conformal risk control
  ([proceedings](https://proceedings.iclr.cc/paper_files/paper/2024/hash/f3549ef9b5ff520a7e41ff3cc306ab2b-Abstract-Conference.html)),
  Xiong et al., Huang et al.
- **ICLR 2025 oral:** Trust or Escalate
  ([proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/08dabd5345b37fffcbe335bd578b15a0-Abstract-Conference.html)).
- **ICML 2024:** conformal factuality
  ([PMLR 235](https://proceedings.mlr.press/v235/mohri24a.html)). It gives
  80-90% correctness guarantees while keeping most of the output, and is
  relevant to ticket 41's cell-by-cell back-off.
- **Other venues:** Conformal Language Modeling (ICLR 2024,
  [arXiv](https://arxiv.org/abs/2306.10193)); MIPRO (EMNLP 2024); GEPA (ICLR
  2026); semantic entropy (Nature 630, 2024); Tian et al. (EMNLP 2023).
- **Preprints:** Yadkori et al., SkillsBench, Liu et al. 2026, Brown et al.
- **Unverified:** the venues of Liu et al. 2021 (cited by arXiv) and of
  Gibbs & Candès (NeurIPS 2021, from memory); Strata's support for logprobs,
  `response_format` and multiple samples; DW1's mail volumes.

## Measured after writing (2026-11-16, Strata on the home lab)

The three "not verified" points about Strata, one request each:

- **Token probabilities: yes.** `logprobs: true, top_logprobs: 3` returns
  each token's log-probability and the alternatives (a yes/no answer came
  back `Yes` at -0.118 with `No` at -2.443), so a token-level confidence is
  available alongside sample agreement.
- **JSON-schema constraints: yes.** `response_format: {type: json_schema,
  strict: true}` with an `enum` answered only a member of the enum.
- **Concurrent requests: yes.** Four requests at once finished in about the
  time of one (about 1 s), so several samples per item are affordable.
