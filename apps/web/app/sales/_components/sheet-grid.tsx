"use client";

import { Alert, theme } from "antd";
import { StatusTag } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { label, REGION_FLAG } from "../_lib/labels";

type Grid = SalesSchemas["SheetGrid"];
type Cell = SalesSchemas["SheetCell"];

/** "A", "B", … "AA": the column letters a spreadsheet prints. */
function columnName(index: number): string {
  let name = "";
  for (let n = index; n > 0; n = Math.floor((n - 1) / 26))
    name = String.fromCharCode(65 + ((n - 1) % 26)) + name;
  return name;
}

function cellFlags(cell: Cell): string[] {
  const flags: string[] = [];
  if (cell.hidden_row) flags.push(label(REGION_FLAG, "hidden_row"));
  if (cell.hidden_column) flags.push(label(REGION_FLAG, "hidden_column"));
  if (cell.font_matches_fill)
    flags.push(label(REGION_FLAG, "font_matches_fill"));
  if (cell.formula_without_cached_value)
    flags.push(label(REGION_FLAG, "formula_without_cached_value"));
  return flags;
}

/**
 * A sheet of the original workbook as its cells, with the cells a value was
 * read from marked on the grid (spec decision 12): the cell text as text,
 * never a picture and never the extracted value. A cell a person looking at
 * the workbook would not see (a hidden row or column, text the colour of its
 * fill, a formula without a cached value) says so in words.
 *
 * The workbook's own colours are not reproduced: they are data, not the
 * theme's, and a flag says what they hide.
 */
export function SheetGrid({
  grid,
  marked,
  focused,
}: {
  grid: Grid;
  /** Cell refs ("D10") a value on the case was read from, with their field. */
  marked: Map<string, string>;
  focused: string | null;
}) {
  const { token } = theme.useToken();
  const cells = new Map(
    grid.cells.map((cell) => [`${cell.row}:${cell.column}`, cell]),
  );
  const rows = Array.from({ length: grid.rows }, (_, i) => i + 1);
  const columns = Array.from({ length: grid.columns }, (_, i) => i + 1);

  return (
    <div className="space-y-2">
      {grid.hidden_sheet ? (
        <Alert
          type="warning"
          showIcon
          title={`${label(REGION_FLAG, "hidden_sheet")}: người mở file sẽ không thấy sheet này.`}
        />
      ) : null}
      {grid.truncated ? (
        <Alert
          type="warning"
          showIcon
          title="Sheet quá lớn để hiển thị hết"
          description="Chỉ hiện phần đầu của sheet theo giới hạn ô của quy tắc đơn hàng. Các giá trị đã đọc vẫn có ô nguồn riêng."
        />
      ) : null}
      <div
        className="max-h-[70vh] overflow-auto"
        tabIndex={0}
        aria-label={`Sheet ${grid.sheet}`}
      >
        <table
          className="border-collapse tabular-nums"
          style={{
            fontSize: token.fontSizeSM,
            borderColor: token.colorBorderSecondary,
          }}
        >
          <thead>
            <tr>
              <th scope="col" style={{ background: token.colorFillAlter }} />
              {columns.map((c) => (
                <th
                  key={c}
                  scope="col"
                  className="px-2 py-1"
                  style={{
                    background: token.colorFillAlter,
                    border: `1px solid ${token.colorBorderSecondary}`,
                  }}
                >
                  {columnName(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r}>
                <th
                  scope="row"
                  className="px-2 py-1 text-right"
                  style={{
                    background: token.colorFillAlter,
                    border: `1px solid ${token.colorBorderSecondary}`,
                  }}
                >
                  {r}
                </th>
                {columns.map((c) => {
                  const cell = cells.get(`${r}:${c}`);
                  const ref = `${columnName(c)}${r}`;
                  const field = marked.get(ref);
                  const isFocused = focused === ref;
                  const flags = cell ? cellFlags(cell) : [];
                  return (
                    <td
                      key={c}
                      className="px-2 py-1 align-top"
                      data-cell={ref}
                      title={field ? `${ref}: ${field}` : ref}
                      style={{
                        border: `1px solid ${token.colorBorderSecondary}`,
                        outline: field
                          ? `${isFocused ? 3 : 2}px solid ${isFocused ? token.colorWarning : token.colorPrimary}`
                          : undefined,
                        outlineOffset: -2,
                        background: isFocused
                          ? token.colorWarningBg
                          : field
                            ? token.colorPrimaryBg
                            : undefined,
                        minWidth: 48,
                        maxWidth: 360,
                      }}
                    >
                      <span className="whitespace-pre-wrap break-words">
                        {cell?.text ?? ""}
                      </span>
                      {flags.map((flag) => (
                        <span key={flag} className="ms-1">
                          <StatusTag tone="unk">{flag}</StatusTag>
                        </span>
                      ))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
