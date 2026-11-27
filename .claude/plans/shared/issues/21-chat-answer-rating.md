# 21 — Rate an answer: useful / not right, kept for the eval

Status: ready-for-agent
Blocked by: none
Category: chat / evaluation

## What

§1: "Nút thích/không thích câu trả lời, lưu lại làm ví dụ". Checked
2026-11-27: not built. The frame's locale already words "Hữu ích" / "Chưa
đúng" (`packages/typescript/ui/src/assistant-chat.tsx:46-47`) but no control
uses them and nothing stores a rating. Sales ticket 57 waits on "the PICs'
real replies" for the chat's eval.

## Design

- **Stored with the turn, by its asker only:** `sales.assistant_turns`
  gains `rating` (`useful|not_right`, CHECK), `rating_note` (bounded with
  `char_length`), `rated_at` (migration). `POST
  /api/v1/sales/assistant/turns/{seq}/rating`; the conversation is the
  person's own (RLS by user), so nobody rates another's answer.
- **A rating is not an example by itself:** a "Chưa đúng" with its note
  enters the labelling queue ticket 57 reads (a candidate eval case), and a
  person decides whether it becomes one; the answer's text and cites go with
  it, the case's amounts never.
- **The frame:** `AssistantChat` gets `onRate(turn, rating, note?)`; antd X
  `Actions` feedback under each finished answer; "Chưa đúng" opens a short
  note field.

## Acceptance

- API: rating one's own turn; another person's turn 404; another tenant's
  404 (PostgreSQL); a rating on a turn still streaming refused.
- Unit: a "not right" lands in the labelling queue, a "useful" does not.
- Vitest: the control's states.

## Owed

- none.
