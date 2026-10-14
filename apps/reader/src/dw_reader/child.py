"""One reading process: `python -m dw_reader.child`, started by the service
in a fresh directory holding `request.json`, under the limits the shell set
before it (`dw_reader.reading`). It answers in `result.json` and exits.

An exception is not caught: the process exits non-zero with its traceback on
stderr, which the service keeps for its length only, and the caller is told
the reading crashed. Nothing here touches the network, a database or a
secret; the container it runs in has none of them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from dw_reader.reading import REQUEST, RESULT
from dw_sales.adapters.reader_wire import ReaderRequest
from dw_sales.adapters.readers.operations import handle


def main() -> None:
    request = ReaderRequest.model_validate_json(Path(REQUEST).read_bytes())
    reply = asyncio.run(handle(request))
    Path(RESULT).write_text(reply.model_dump_json(), encoding="utf-8")


if __name__ == "__main__":
    main()
