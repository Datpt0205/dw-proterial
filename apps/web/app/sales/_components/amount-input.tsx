"use client";

import { useEffect, useState } from "react";
import { Input, type InputProps } from "antd";
import {
  formatAmountInput,
  formatMoney,
  parseAmountInput,
  type Currency,
} from "../../../lib/money";

/**
 * An amount or quantity field (ui-quality §9): the person types or pastes in either
 * grouping, the field regroups on blur without moving the caret while typing,
 * and what was understood is written under it in the currency's format. The
 * value it hands the form is the decimal string the API takes, or "" when the
 * text cannot be read, which the form's rule then refuses.
 */
export function AmountInput({
  value,
  onChange,
  currency,
  ...props
}: Omit<InputProps, "value" | "onChange"> & {
  value?: string;
  onChange?: (value: string) => void;
  /** The currency the figure is in; none for a quantity or a count. */
  currency?: Currency;
}) {
  const [text, setText] = useState(formatAmountInput(value));
  useEffect(() => {
    if (value !== parseAmountInput(text)) setText(formatAmountInput(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  const parsed = parseAmountInput(text);
  return (
    <div>
      <Input
        {...props}
        inputMode="decimal"
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          onChange?.(parseAmountInput(event.target.value) ?? "");
        }}
        onBlur={(event) => {
          if (parsed !== null) setText(formatAmountInput(parsed));
          props.onBlur?.(event);
        }}
        suffix={currency ? (currency === "VND" ? "đ" : currency) : undefined}
      />
      {parsed !== null && text && currency ? (
        <span aria-live="polite">= {formatMoney(parsed, currency)}</span>
      ) : null}
    </div>
  );
}
