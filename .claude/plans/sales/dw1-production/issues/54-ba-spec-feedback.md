# 54 — Feedback to the BA on the DW1 spec of 20.11, with Bravo's evidence

Status: in progress (document written 2026-11-20: `docs/proterial/Gop-y-dac-ta-DW1_2026-11-20.docx`, gitignored; Đạt sends it to the BA)
Blocked by: none
Category: documentation

## Why

The BA's `DAC_TA_DW1_SALES_CHO_IT_DEV_20.11.2026.docx` (`Downloads/DW1.zip`)
has the right frame but is not yet ready for developers. The 11-20 review ran
in two passes and was checked against Bravo's procedures. It found:

- contradictions between the spec, the workbook and the diagrams;
- loops with no exit;
- steps that assume Bravo behaves otherwise than it does.

The summary is in `sales.md`, 11-20.

## Shape

A document in Vietnamese for the BA.

- Each finding carries its spec line and UC/BR code, and one of three marks:
  - "settled by Bravo", naming the object that proves it;
  - "decided by Đạt 11-20";
  - "Proterial decides".
- It includes:
  - the corrected 7.2 mapping to template 72;
  - the Bravo checks the spec should reuse instead of specifying them again;
  - the questions still open: the QM/QN/QS criteria and the JP signature;
    old quotations of a TDC customer turned FG.

## Acceptance

Đạt sends the document, and the BA's next version answers each finding.

## Comments
