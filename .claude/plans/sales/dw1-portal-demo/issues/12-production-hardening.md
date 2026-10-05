# 12 — Production hardening (before any real Proterial data)

Status: needs-triage
Blocked by: 09

What the demo deliberately leaves out, and which must land before DW1 reads
a real document or serves a real tenant. Each item may become its own ticket
when triaged.

- **Tenant overrides of rules and templates (G15, decision 14).**
    - Resolve `sales_order_rules`, `sales_quote_rules`, `sales_pricing`,
      `sales_kpi`, `sales_emails` and `sales_bravo_upload` through
      `TenantOverlay`, with the tenant layer read through
      `PolicyOverridePort`.
    - Add a propose/approve route. Approval needs `sales.rules.approve` (on
      `sales_head`; the scope is declared with this route), and the proposer
      cannot approve their own version.
    - Audit each change.
    - Test: a tenant override never resolves for another tenant.
- **Approval matrix (G6).** When Proterial sends who approves which price
  or discount (requirements doc §4 item 5), it becomes a ladder in
  `sales_pricing`. Each step names a scope that a role or permission set in
  the sales migration grants, and a schema check refuses a step naming any
  other scope. The quote stamps its step at submit. Until then any holder of
  `sales.quote.approve` other than the pricer approves.
- **Case reassignment (G22).** A reassign route for `sales_head`, declaring
  `sales.case.assign` with it, audited. Until it exists, `assigned_to` is
  only the stamp from the customer's Sales PIC, and unassigned cases show
  to every PIC.
- **Sandboxed parsing (G17, decision 13).**
    - Parsing runs in the worker under the docgen containment: no network,
      ulimit, wall clock and output cap.
    - A malware scan and format check come first (ADR 0010 decision 6).
    - Legacy `.xls`/`.doc` are converted in the sandbox; encrypted files are
      refused; image PDFs are OCRed per ADR 0009 and 0010.
    - The API stops parsing.
- **Legacy Vietnamese encodings (G37).** Detect TCVN3/VNI font names in xlsx
  styles and PDF fonts. Raise `legacy_encoding` (blocking; no attribute
  matching) until the text is converted per ADR 0010 decision 3. Add one
  fixture.
- **Real PO shapes (G36).** A line with several delivery schedules keeps all
  of them, giving one upload row per schedule as the Bravo template
  requires.
- **Real Bravo history (G18).** A Bravo adapter for `orders_for_po`,
  `orders_since` and `open_ycbg`, through an anti-corruption layer.
- **Support access without prices (G20, dw_sales ADR 0003).**
    - The ADR 0008 grant, issued by a `sales_head`, carries only
      `{sales.overview.read, sales.case.read}`.
    - Negative tests under a support context on orders, quotes, evidence,
      the source view, downloads, the overview and the audit log.
    - No FPT identity holds a `sales_*` role or `platform_admin` in the
      customer's tenant.
- **Retention (G29).** Name a retention rule for sales cases, artifacts and
  served-source records once Proterial answers (requirements doc §3.1).
- **Classification and telemetry (G32).**
    - A span-attribute allowlist for sales components.
    - A test that a processed PO's prices, names and email text appear in no
      captured span, log or error response.
    - The data-plane placement follows the deployment answer.
- **Export control (G35).** An NOEC request draft when the NOC is missing,
  and the denial-list result read from Proterial's real list.
- **Mail authentication (G39).** The real inbox adapter fills
  SPF/DKIM/DMARC from the mail system's headers, which the mock currently
  stubs.
- **Public-repo guard (G34).** Extend the "no customer data" guard from the
  fixtures to `git ls-files`, with a deny-list kept outside git. Whether to
  alias the customer and procedure codes is owed by Đạt.
