# 09 — Evals, security review, demo run

Status: ready-for-agent
Blocked by: 08

## What

- `evals/datasets/sales@1.0.0.json` with prompt_injection,
  cross_tenant_attack and missing_evidence cases.
- Graders `sales.extraction_accuracy` and `sales.findings_recall` (G14, G30):
    - `sales.extraction_accuracy` scores PRV code, quantity, unit price and
      requested date against `purchase_orders.json`;
    - `sales.findings_recall` scores against the README's expected findings.

    Both graders live in `dw_sales`, and a composition root injects them into
    the eval runner, so `dw_evals` never imports a context. They run unchanged
    on Proterial's sample set, which is kept outside git.

- Security cases:
    - M12 (injection);
    - tenant B on mocks bound per tenant (red when the binding is removed);
    - missing_evidence on the TOTAL-mismatch and skipped-line fixtures;
    - maker = checker;
    - pricer = approver;
    - price leakage through `GET /audit/events` and notifications.
- Run `reviewing-feature-security`, `reviewing-deployment-security` and the
  mutation check. Each new guard is shown red when removed.
- A full demo rehearsal on the running stack, as the personas. Record the
  steps in the area file.
