"""Every environment knob the reader sandbox reads, in one place (sales ticket 25).

The numbers are the containment budget of one reading process. The question
each answers is the docgen sandbox's: "what does a hostile file get?". A file
of the sender's choosing is parsed here by pypdf, openpyxl, LibreOffice and
Tesseract (ticket 27), so a parser bug it triggers must find a process with no
network, nothing worth reading, a short life and a small budget.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

MEGABYTE = 1024 * 1024


class ReaderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DW_READER_", extra="ignore")

    # tmpfs in the container, a real directory in tests. Each request gets a
    # directory of its own under it, removed when the answer is read.
    root: str = "/work"

    # Where the service listens: a Unix socket on a volume only the api and
    # worker containers mount. The container itself has no network at all.
    socket_path: str = "/run/dw-reader/reader.sock"

    # bash, not `/bin/sh`: dash's `ulimit` has no `-u` (`DocgenSettings`).
    shell_path: str = "/bin/bash"

    # One reading process at a time. They share a uid, and two tenants' files
    # read at once would be one compromised parser away from each other's
    # directory; serial reading is what keeps a request's files its own.
    max_concurrency: int = 1

    # The wall clock of one reading process, killed with its process group
    # past it. A text PO reads in well under a second; OCR of a scanned page
    # takes seconds (ticket 27, measured on the image after the reboot).
    read_seconds: int = 120

    # CPU seconds, the backstop behind the wall clock (`DocgenSettings`).
    cpu_seconds: int = 150
    # LibreOffice maps about 500 MB on a first run; a memory bomb dies here.
    address_space_mb: int = 2048
    max_open_files: int = 256
    # Per uid, the service's own threads included: LibreOffice and Tesseract
    # start a few processes and threads of their own.
    max_processes: int = 256
    # Any one file a reading process writes: a converted workbook or PDF, a
    # page image for OCR, its answer.
    max_file_bytes: int = 64 * MEGABYTE

    # What the reading process prints (a traceback, a tool's complaint). Kept
    # for its length only: it may quote the file.
    max_output_bytes: int = 64 * 1024

    # One request: an attachment the order rules let a reader open (10 MB
    # today) as base64, with room for its description and arguments.
    max_request_bytes: int = 32 * MEGABYTE
    # One answer: a sheet grid of a thousand rows is the largest.
    max_result_bytes: int = 32 * MEGABYTE

    @property
    def enforce_limits(self) -> bool:
        """Whether `ulimit` applies: False on Windows, where the service runs
        only under unit tests. The image is Linux, so the limits are on
        wherever a file of a sender's is read."""
        return os.name == "posix"


@lru_cache(maxsize=1)
def get_settings() -> ReaderSettings:
    return ReaderSettings()
