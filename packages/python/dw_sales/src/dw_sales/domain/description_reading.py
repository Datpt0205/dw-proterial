"""A model's reading of an item description, and what code accepts of it.

`descriptions.read_description` reads only the words of DW1's own vocabulary,
in the mock customers' word order; anything else is "not understood" and the
line stays `code_unmapped` for Sales to look up. Where a tenant turns it on
(`sales_order_rules.model_assist.description_attributes`, dw_sales ADR 0005),
a local model reads those descriptions instead, and this module decides what
of its reading counts. The model interprets; code decides.

**What the model gives** (`ModelDescriptionLine`): per line, a value from a
closed `Literal` set for each categorical attribute, with the text it read the
value from, and for each numeric or free-string attribute only the text. It
never gives a number, a code or a choice.

**What code checks** (`verify_reading`), each a reason the line stays
unmapped (`NotUnderstood`). First, a label given without the text it was
read from, or text without a label, is not evidence and is dropped; check 3
then decides whether every word was still accounted for.

1. Every span is found in the NFKC-normalised description (case folded), and
   exactly once. Not found, found twice, or overlapping another span: not
   understood. A substring test alone proves nothing for a token like ``2``.
2. Cores, gauge, pack length and spec number are parsed from their span by the
   parsers below, full-width digits included (NFKC). A span that does not
   parse is not understood. The model has no value to disagree with.
3. Every character of the description that is not a space or punctuation lies
   inside some span. A word nobody accounted for means not understood, as in
   `read_description`: the model does not get to say which words it skipped.
4. A categorical span holds no digit: a number is a value, and values are read
   by code from a numeric span, never hidden inside a label.
5. The categorical values are the one judgement left to the model. Each is
   marked ``read_by="model"`` and shown with its span to the person who
   confirms the PRV code.

`descriptions.candidates` then runs on the result unchanged; a line read this
way is at best a `candidate`, never `exact` (`orders.OrderLine`).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from typing import Final, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from dw_sales.domain.catalog import Colour, Conductor, ItemFamily, Packaging, Shield, Stranding
from dw_sales.domain.descriptions import StatedAttributes
from dw_sales.domain.spans import FoldedText

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

Span = str
_SPAN = Field(min_length=1, max_length=200)

# Most lines one call reads: the prompt and the answer stay well inside the
# local model's context window (8,192 tokens) whatever the PO holds.
MAX_LINES_PER_READING: Final = 10


class ModelDescriptionLine(BaseModel):
    """One line as the model reads it: flat, so a server can decode it against
    the JSON schema. Every key is required and may be null: a server decoding
    against the schema then has to write each one, where an optional key was
    measured to be left out with its span. Each text comes before its value,
    so the model reads the words before it labels them. Null text: the
    description does not state the attribute."""

    model_config = _FROZEN

    line_no: int = Field(ge=1, le=9999)
    family_span: Span | None = _SPAN
    family: ItemFamily | None
    stranding_span: Span | None = _SPAN
    stranding: Stranding | None
    conductor_span: Span | None = _SPAN
    conductor: Conductor | None
    shield_span: Span | None = _SPAN
    shield: Shield | None
    colour_span: Span | None = _SPAN
    colour: Colour | None
    packaging_span: Span | None = _SPAN
    packaging: Packaging | None
    # Text only: code parses the value (check 2).
    cores_span: Span | None = _SPAN
    gauge_span: Span | None = _SPAN
    pack_length_span: Span | None = _SPAN
    spec_no_span: Span | None = _SPAN


class ModelDescriptionReading(BaseModel):
    """What one call returns: a reading per line it was sent."""

    model_config = _FROZEN

    lines: tuple[ModelDescriptionLine, ...] = Field(max_length=MAX_LINES_PER_READING)


# ------------------------------------------------------- what is stamped --

AttributeName = Literal[
    "family",
    "stranding",
    "conductor",
    "shield",
    "colour",
    "packaging",
    "cores",
    "gauge",
    "pack_length_m",
    "spec_no",
]
CATEGORICAL: Final[tuple[AttributeName, ...]] = (
    "family",
    "stranding",
    "conductor",
    "shield",
    "colour",
    "packaging",
)
# The model's text field for each attribute code parses (check 2).
PARSED: Final[dict[AttributeName, str]] = {
    "cores": "cores_span",
    "gauge": "gauge_span",
    "pack_length_m": "pack_length_span",
    "spec_no": "spec_no_span",
}
ReadBy = Literal["code", "model"]
NotUnderstood = Literal[
    # The model's answer for the line as a whole.
    "line_missing",
    "no_attribute",
    # Check 1.
    "span_not_found",
    "span_repeated",
    "spans_overlap",
    # Check 2.
    "value_unparsed",
    # Check 3.
    "text_uncovered",
    # Check 4.
    "digit_in_label",
    # A value the catalogue's own record refuses (``0`` cores, say).
    "value_refused",
]
ReadingOutcome = Literal["read", "not_understood", "unavailable"]


class SpanRead(BaseModel):
    """One attribute as code accepted it: the text, where it sits in the
    NFKC-normalised description, the value, and who read the value."""

    model_config = _FROZEN

    attribute: AttributeName
    span: str = Field(min_length=1, max_length=200)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    value: str = Field(min_length=1, max_length=64)
    read_by: ReadBy

    @model_validator(mode="after")
    def _who_reads_what(self) -> Self:
        if self.end <= self.start:
            raise ValueError("a span ends after it starts")
        # A number is never the model's: check 2 is what makes it code's.
        if (self.attribute in CATEGORICAL) != (self.read_by == "model"):
            raise ValueError(f"{self.attribute} is read by code, a label by the model")
        return self


class DescriptionReading(BaseModel):
    """What a model reading did for one line, stamped on its check basis.

    ``read``: every check passed, and ``spans`` are what the candidates were
    computed from. ``not_understood``: a check refused it (``reason``).
    ``unavailable``: no usable answer (the model down, timed out, or its
    output invalid); the line is unmapped exactly as without the model.
    """

    model_config = _FROZEN

    # `<prompt_id>@<version>`, the profile and the route the call ran on.
    prompt: str = Field(pattern=r"^[a-z][a-z0-9_.]*@\d+\.\d+\.\d+$")
    model_profile: str = Field(min_length=1, max_length=64)
    route: str = Field(min_length=1, max_length=64)
    outcome: ReadingOutcome
    reason: NotUnderstood | None = None
    spans: tuple[SpanRead, ...] = ()

    @model_validator(mode="after")
    def _outcome_says_what_is_there(self) -> Self:
        read = self.outcome == "read"
        if read != bool(self.spans):
            raise ValueError("a reading holds spans exactly when it was read")
        if (self.outcome == "not_understood") != (self.reason is not None):
            raise ValueError("a reading not understood names why, and only then")
        return self

    @property
    def model_read(self) -> tuple[AttributeName, ...]:
        """The attributes whose value is the model's judgement (check 5)."""
        return tuple(s.attribute for s in self.spans if s.read_by == "model")


# ------------------------------------------------------------ verification --


@dataclass(frozen=True, slots=True)
class Verified:
    """A reading code accepted: what the description states, and the spans."""

    stated: StatedAttributes
    spans: tuple[SpanRead, ...]


def verify_reading(description: str, line: ModelDescriptionLine | None) -> Verified | NotUnderstood:
    """What of the model's reading of ``description`` code accepts (module
    docstring, checks 1-4). Never raises on the model's answer: a reading
    that does not hold is a line Sales maps, not a PO that cannot be read."""
    if line is None:
        return "line_missing"
    text = FoldedText(unicodedata.normalize("NFKC", description))
    claims: list[tuple[AttributeName, str, str | None]] = []
    for name in CATEGORICAL:
        value, span = getattr(line, name), getattr(line, f"{name}_span")
        if value is None or span is None:
            # A label with no text is a guess at what the words do not state
            # (measured: a conductor "read" from a description naming none),
            # and text with no label is words the model could not place.
            # Neither is evidence, so neither is taken; coverage (check 3)
            # then refuses the line if words were left unaccounted for.
            continue
        claims.append((name, span, value))
    for name, field in PARSED.items():
        span = getattr(line, field)
        if span is not None:
            claims.append((name, span, None))
    if not claims:
        return "no_attribute"

    spans: list[SpanRead] = []
    for name, raw_span, label in claims:
        span = unicodedata.normalize("NFKC", raw_span)
        located = text.locate(span)
        if isinstance(located, str):
            return located
        start, end = located
        shown = text.original[start:end]
        if label is not None:
            if any(c.isdigit() for c in shown):
                return "digit_in_label"
            spans.append(
                SpanRead(
                    attribute=name, span=shown, start=start, end=end, value=label, read_by="model"
                )
            )
            continue
        parsed = _PARSERS[name](shown)
        if parsed is None:
            return "value_unparsed"
        spans.append(
            SpanRead(attribute=name, span=shown, start=start, end=end, value=parsed, read_by="code")
        )

    ordered = sorted(spans, key=lambda s: s.start)
    if any(later.start < earlier.end for earlier, later in pairwise(ordered)):
        return "spans_overlap"
    if not _covered(text.original, ordered):
        return "text_uncovered"
    try:
        stated = StatedAttributes.model_validate({s.attribute: _typed(s) for s in ordered})
    except ValidationError:
        return "value_refused"
    return Verified(stated=stated, spans=tuple(ordered))


def _covered(text: str, spans: list[SpanRead]) -> bool:
    """Every character that is not a space or punctuation lies inside a span."""
    inside = [False] * len(text)
    for span in spans:
        for index in range(span.start, span.end):
            inside[index] = True
    return all(
        inside[index] or char.isspace() or unicodedata.category(char).startswith("P")
        for index, char in enumerate(text)
    )


# ----------------------------------------------------------------- parsers --
# Deterministic, from the span alone. Each accepts one number and one
# spelling of its attribute's unit, and nothing else. The unit is required:
# it is what says a number is a core count and not a length, so a bare "305"
# is no attribute at all rather than whichever one the model guessed. A unit
# the parser does not know ("1 KM", "100 FT") is never read as metres.

_CORES = re.compile(r"(\d{1,3})\s*-?\s*(?:c|cores?|cond|lõi|ruột|芯|心|x|\u00d7)", re.IGNORECASE)
_AWG = re.compile(r"awg\s*-?\s*#?\s*(\d{1,2})|#?\s*(\d{1,2})\s*-?\s*awg", re.IGNORECASE)
_SECTION = re.compile(r"(\d{1,2})[.,](\d{1,2})\s*(?:mm2|mm\^2|sqmm|sq\.?\s*mm|sq)", re.IGNORECASE)
_METRES = re.compile(r"(\d{1,6})\s*(?:m|mtrs?|meters?|metres?|mét|met|メートル)", re.IGNORECASE)
_SPEC = re.compile(
    r"(?:spec(?:\.|\s*no\.?)?|仕様(?:書)?|quy\s*cách|tiêu\s*chuẩn)?\s*[:#]?\s*([a-z0-9][a-z0-9/-]{1,31})",
    re.IGNORECASE,
)


def parse_cores(span: str) -> str | None:
    match = _CORES.fullmatch(span.strip())
    if match is None or not 1 <= int(match.group(1)) <= 100:
        return None
    return str(int(match.group(1)))


def parse_gauge(span: str) -> str | None:
    """``AWG24`` or a cross-section such as ``0.5mm2``: the item master's spellings."""
    text = span.strip()
    if match := _AWG.fullmatch(text):
        return f"AWG{int(match.group(1) or match.group(2))}"
    if match := _SECTION.fullmatch(text):
        whole, fraction = match.group(1), match.group(2).rstrip("0") or "0"
        return f"{int(whole)}.{fraction}mm2"
    return None


def parse_pack_length(span: str) -> str | None:
    match = _METRES.fullmatch(span.strip())
    if match is None or int(match.group(1)) == 0:
        return None
    return str(int(match.group(1)))


def parse_spec_no(span: str) -> str | None:
    match = _SPEC.fullmatch(span.strip())
    if match is None:
        return None
    number = match.group(1).upper()
    # A spec number carries a digit; a word alone is no number.
    return number if any(c.isdigit() for c in number) else None


_PARSERS: Final = {
    "cores": parse_cores,
    "gauge": parse_gauge,
    "pack_length_m": parse_pack_length,
    "spec_no": parse_spec_no,
}


def _typed(span: SpanRead) -> object:
    if span.attribute == "cores":
        return int(span.value)
    if span.attribute == "pack_length_m":
        return Decimal(span.value)
    return span.value


def vocabulary() -> dict[str, tuple[str, ...]]:
    """The closed sets a categorical value comes from, built from `catalog.py`
    so the prompt never holds a second copy of them."""
    return {
        "family": get_args(ItemFamily),
        "stranding": get_args(Stranding),
        "conductor": get_args(Conductor),
        "shield": get_args(Shield),
        "colour": get_args(Colour),
        "packaging": get_args(Packaging),
    }
