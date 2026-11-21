"""An Import template read into which sheet column each field comes from
(ticket 51). The XML here is synthetic, in the shape Bravo stores."""

from __future__ import annotations

import pytest

from dw_bravo.expression import UndecidableError
from dw_bravo.import_template import read_import_template

pytestmark = pytest.mark.unit

_TEMPLATE = (
    "<root><Tables>"
    "<BizDoc><nSelectedSheetIndex>0</nSelectedSheetIndex>"
    "<Cols><DocDate>B</DocDate><CustomerCode>G</CustomerCode></Cols>"
    "<txtRowRange>4</txtRowRange></BizDoc>"
    "<Detail><nSelectedSheetIndex>0</nSelectedSheetIndex><txtForeignKey>A</txtForeignKey>"
    "<txtParentKey>A</txtParentKey><txtRowRange>4</txtRowRange>"
    "<Cols><POLine>S</POLine><Quantity9>AA</Quantity9></Cols></Detail>"
    "</Tables></root>"
)


def test_each_field_reads_its_column_and_the_lines_join_on_their_key() -> None:
    template = read_import_template(_TEMPLATE)

    header, detail = template.tables["BizDoc"], template.tables["Detail"]
    assert dict(header.columns) == {"DocDate": "B", "CustomerCode": "G"}
    assert dict(detail.columns) == {"POLine": "S", "Quantity9": "AA"}
    assert (header.first_row, detail.foreign_key, detail.parent_key) == (4, "A", "A")
    assert template.columns_read() == {"A", "B", "G", "S", "AA"}


@pytest.mark.parametrize(
    "xml",
    [
        "not xml",
        "<root><Other/></root>",
        _TEMPLATE.replace("<txtRowRange>4</txtRowRange></BizDoc>", "<Formula>x</Formula></BizDoc>"),
        _TEMPLATE.replace("<DocDate>B</DocDate>", "<DocDate>B2</DocDate>"),
        _TEMPLATE.replace("<DocDate>B</DocDate>", "<DocDate>B</DocDate><DocDate>C</DocDate>"),
        _TEMPLATE.replace(
            "<txtRowRange>4</txtRowRange></BizDoc>", "<txtRowRange>x</txtRowRange></BizDoc>"
        ),
        "<root><Tables></Tables></root>",
    ],
    ids=[
        "not_xml",
        "no_tables",
        "unknown_part",
        "not_a_column",
        "field_twice",
        "row_not_number",
        "empty",
    ],
)
def test_a_template_with_anything_unknown_is_refused_whole(xml: str) -> None:
    with pytest.raises(UndecidableError):
        read_import_template(xml)
