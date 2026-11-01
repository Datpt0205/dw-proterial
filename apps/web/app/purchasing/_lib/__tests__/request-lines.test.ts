// @vitest-environment node
import { describe, expect, it } from "vitest";
import { linesOut } from "../../_components/request-lines";

describe("a request's lines as the API takes them", () => {
  it("numbers them as shown and reads Vietnamese decimals, blanks as none", () => {
    expect(
      linesOut([
        {
          description: " Găng tay ",
          quantity: "12,5",
          unit: "hộp",
          estimated_unit_price: "150.000",
        },
        {
          item_code: " DC-200 ",
          description: "Dao cắt",
          quantity: "2",
          unit: "cái",
        },
      ]),
    ).toEqual([
      {
        line_no: 1,
        item_code: null,
        description: "Găng tay",
        quantity: "12.5",
        unit: "hộp",
        need_by: null,
        estimated_unit_price: "150000",
      },
      {
        line_no: 2,
        item_code: "DC-200",
        description: "Dao cắt",
        quantity: "2",
        unit: "cái",
        need_by: null,
        estimated_unit_price: null,
      },
    ]);
  });
});
