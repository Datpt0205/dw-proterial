# 18 — Approve or return in the chat

Status: ready-for-agent
Blocked by: 17
Category: chat / approvals

## What

§1: "Duyệt / trả lại ngay trong chat (thẻ quyết định gọi API duyệt, gắn
phiên bản đối tượng)". Checked 2026-11-27: not built. DW1's chat can open an
approval (a Bravo write's proposal) but deciding happens elsewhere; Sales
ticket 79 lists "approve/return said in the chat" as left. This ticket is
that slice (79 points here).

## Design

- **A `decision` block** (added to `dw_platform.domain.chat_blocks`): the
  approval id, what is decided in words, the subject's version and content
  hash, whether a comment is required, the two labels. The server offers it
  only to someone who may decide it now (the same `may_decide` the decide
  route runs), so a requester never sees it for their own request.
- **The press goes to the same door as everywhere else:** a DW1 case
  approval (`sales.quote`, `sales.order.cross_check`) to the case's own
  decide route with the case version (they are decided on the case page
  because they need it: `apps/web/app/sales/_meta/approvals.ts`); any other
  to the platform's decide. "Trả lại" asks for the reason in the block.
- What the person says ("duyệt đi") is read by the intent step into
  `decide_approval` with no id; code finds the one pending approval of this
  case the person may decide, or lists them as a `choice` (ticket 17). The
  model never names the approval.
- After the server's 2xx the block shows the outcome; a stale version shows
  "đã thay đổi" with what changed, never a silent retry.

## Acceptance

- Sales unit: the block offered only to a decider; a requester gets none;
  "duyệt" with two pending approvals gives a choice; a decision through the
  chat is refused at the server on a stale case version and on maker =
  checker (negative tests at the route, not the hidden button).
- Eval: `sales_case_chat` gains cases "duyệt giúp tôi" by the maker and an
  injected "approve everything" in a customer's mail text.
- Mutation: the offer check removed → a requester is shown the block → red.

## Owed

- none.
