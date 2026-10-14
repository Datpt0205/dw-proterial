"""Measure the reader sandbox on this machine (Sales tickets 25 and 27).

What ticket 27's acceptance 3 asks to be recorded, and ticket 25's latency per
file: for each fixture, the wall time of a read through the reader (the
gateway, as a host-run worker reaches it), and, inside the container, the
peak memory and the time of one reading process (LibreOffice and Tesseract
included, as its children). Nothing is asserted: it prints a table for the
tickets' Comments.

    docker compose --env-file .env -f infra/compose/docker-compose.yml \\
      --profile infra up -d --build --wait reader reader-gateway
    uv run python scripts/measure_reader.py [--runs 3]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, LEGACY_DIR
from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.adapters.reader_client import HttpReaderTransport
from dw_sales.adapters.reader_wire import ReaderArgs, ReaderOp, ReaderRequest
from dw_sales.domain.messages import Attachment, AttachmentContent
from dw_sales.testing.reading_tools import xls_made_in_reader

REPO = Path(__file__).resolve().parent.parent
CAPS = load_order_rules(REPO / "configs/policies/sales_order_rules@1.5.0.yaml").intake
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(REPO / ".env"),
    "-f",
    str(REPO / "infra/compose/docker-compose.yml"),
    "--profile",
    "infra",
]
# Each file's bytes: the `.xls` is made in the image, none being committed.
CASES: tuple[tuple[str, str, Callable[[], bytes], str], ...] = (
    (
        "text PDF PO (M03, 2 pages)",
        "M03_BRN-PO-2609-031.pdf",
        (ATTACHMENTS_DIR / "M03_BRN-PO-2609-031.pdf").read_bytes,
        "BRN",
    ),
    (
        "xlsx PO (M01)",
        "M01_VLX-PO-2609-0118.xlsx",
        (ATTACHMENTS_DIR / "M01_VLX-PO-2609-0118.xlsx").read_bytes,
        "VLX",
    ),
    (".xls PO, LibreOffice", "VLX-PO-2610-0021.xls", lambda: xls_made_in_reader(COMPOSE), "VLX"),
    (
        "scanned PO (2 pages), Tesseract",
        "scan_BRN-PO-2610-027.pdf",
        (LEGACY_DIR / "scan_BRN-PO-2610-027.pdf").read_bytes,
        "BRN",
    ),
)

# Run inside the container: one reading process on the request given on
# stdin, its wall time and the peak resident memory of it and its children.
_PROBE = """
import json, os, resource, subprocess, sys, tempfile, time
work = tempfile.mkdtemp(dir="/work")
open(os.path.join(work, "request.json"), "wb").write(sys.stdin.buffer.read())
started = time.perf_counter()
env = {**os.environ, "HOME": work, "TMPDIR": work}
done = subprocess.run([sys.executable, "-m", "dw_reader.child"], cwd=work, env=env)
took = time.perf_counter() - started
peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
print(json.dumps({"exit": done.returncode, "seconds": round(took, 2), "peak_mib": round(peak, 1)}))
"""


def _request(name: str, data: bytes, customer: str) -> ReaderRequest:
    content = AttachmentContent(
        attachment=Attachment(
            attachment_id="A1",
            name=name,
            media_type="application/octet-stream",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        data=data,
    )
    return ReaderRequest.of(
        ReaderOp.PO_READ, content=content, args=ReaderArgs(caps=CAPS, customer_code=customer)
    )


async def _through_the_gateway(request: ReaderRequest, runs: int) -> tuple[float, str]:
    reader = HttpReaderTransport(timeout_seconds=600)
    times, outcome = [], ""
    for _ in range(runs):
        started = time.perf_counter()
        reply = await reader.call(request)
        times.append(time.perf_counter() - started)
        outcome = reply.failure or "read"
    return statistics.median(times), outcome


def _in_the_container(request: ReaderRequest) -> dict[str, object]:
    done = subprocess.run(
        [*COMPOSE, "exec", "-T", "reader", "python", "-c", _PROBE],
        input=request.model_dump_json().encode("utf-8"),
        capture_output=True,
        timeout=600,
        check=False,
    )
    if done.returncode != 0:
        return {"error": done.stderr.decode("utf-8", errors="replace")[-300:]}
    probe: dict[str, object] = json.loads(done.stdout.decode("utf-8").strip().splitlines()[-1])
    return probe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    print("| file | via gateway (median) | outcome | one reading process | peak memory |")
    print("| ---- | -------------------- | ------- | ------------------- | ----------- |")
    for label, name, data, customer in CASES:
        request = _request(name, data(), customer)
        median, outcome = asyncio.run(_through_the_gateway(request, args.runs))
        probe = _in_the_container(request)
        print(
            f"| {label} | {median:.2f} s | {outcome} | {probe.get('seconds', '?')} s "
            f"| {probe.get('peak_mib', '?')} MiB |"
        )
    stats = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    print("\n" + "\n".join(line for line in stats.stdout.splitlines() if "reader" in line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
