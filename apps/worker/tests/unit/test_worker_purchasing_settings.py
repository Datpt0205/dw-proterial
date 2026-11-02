"""The worker and the API agree on which mailbox DW2 reads: one variable,
`DW_PURCHASING_MAILBOX`, so the API never shows one mailbox while the
worker's lanes work another. Only the worker names the drop folder."""

from __future__ import annotations

import pytest

from dw_api.settings import ApiSettings
from dw_worker.settings import WorkerSettings

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DW_PURCHASING_MAILBOX", "DW_PURCHASING_MAIL_DROP_DIR"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("named", [None, "mock", "stored"])
def test_both_read_the_same_mailbox(monkeypatch: pytest.MonkeyPatch, named: str | None) -> None:
    if named is not None:
        monkeypatch.setenv("DW_PURCHASING_MAILBOX", named)
    worker = WorkerSettings()
    api = ApiSettings()
    assert worker.purchasing_mailbox == api.purchasing_mailbox == (named or "mock")


def test_another_mailbox_is_refused_by_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DW_PURCHASING_MAILBOX", "graph")
    for settings in (WorkerSettings, ApiSettings):
        with pytest.raises(ValueError, match=r"(?i)purchasing_mailbox"):
            settings()


def test_the_drop_folder_is_the_worker_s_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    assert WorkerSettings().purchasing_mail_drop_dir is None
    monkeypatch.setenv("DW_PURCHASING_MAIL_DROP_DIR", "/purchasing-mail-drop")
    assert WorkerSettings().purchasing_mail_drop_dir == "/purchasing-mail-drop"
    assert not hasattr(ApiSettings(), "purchasing_mail_drop_dir")
