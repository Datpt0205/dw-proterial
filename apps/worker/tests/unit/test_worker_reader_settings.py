"""Sales ticket 25: a deployed worker reads every attachment in the reader
sandbox. `DW_SALES_READER=in_process` is for a host-run local worker, and is
refused twice: at startup, and where the transport is built."""

from __future__ import annotations

import pytest

from dw_sales.adapters.reader_client import HttpReaderTransport
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_worker.main import sales_reader
from dw_worker.settings import WorkerSettings

pytestmark = pytest.mark.unit

_DEMO = {
    "sales_demo_tenant_id": "00000000-0000-0000-0000-0000000000a1",
    "sales_demo_workspace_id": "00000000-0000-0000-0000-0000000000a2",
}


def _settings(**values: object) -> WorkerSettings:
    return WorkerSettings(  # type: ignore[call-arg]
        database_url="postgresql+asyncpg://dw_app@db:5432/dw",
        sales_malware_scan="clamd",
        embedding_provider="openai_compatible",
        **_DEMO,
        **values,
    )


@pytest.mark.parametrize("profile", ["uat", "production"])
def test_a_deployed_profile_refuses_reading_outside_the_sandbox(profile: str) -> None:
    settings = _settings(profile=profile, sales_reader="in_process")

    with pytest.raises(RuntimeError, match="DW_SALES_READER=in_process"):
        settings.validate_for_profile()
    with pytest.raises(RuntimeError, match="DW_SALES_READER=in_process"):
        sales_reader(settings)


def test_a_local_worker_may_read_in_process() -> None:
    assert isinstance(sales_reader(_settings(sales_reader="in_process")), InProcessReaderTransport)


def test_the_sandbox_is_read_over_its_socket_where_one_is_mounted() -> None:
    reader = sales_reader(_settings(sales_reader_socket="/run/dw-reader/reader.sock"))

    assert isinstance(reader, HttpReaderTransport)
    assert reader.socket_path == "/run/dw-reader/reader.sock"


def test_the_sandbox_is_the_default() -> None:
    reader = sales_reader(_settings())

    assert isinstance(reader, HttpReaderTransport)
    assert (reader.socket_path, reader.base_url) == (None, "http://127.0.0.1:8120")
