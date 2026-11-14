"""Whose mail a sender's is where companies share a mail domain (dw_sales
ticket 20, ADR 0009 decision 5): `SnapshotSalesCatalog.customer_by_sender`
reads a customer's contacts first, then the sender ledger, never against
those contacts, and the domain only where no address matched and the
tenant's order rules do not mark it shared. The flow through intake and
Sales' confirmation is `test_a_shared_domain_routes_an_unknown_address_...`
below; the SQL ledger's half is `tests/integration/test_recorded_senders_db.py`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dw_kernel.ports import FixedClock
from dw_platform.domain.messages import EmailAddress
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.adapters.order_rules import load_tenant_order_rules
from dw_sales.application.ports import SalesScope
from dw_sales.application.snapshot_catalog import ApprovedList, SnapshotSalesCatalog
from dw_sales.domain.catalog import Customer
from dw_sales.domain.master_data import CatalogList
from dw_sales.domain.order_checks import OrderRules
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import ALPHA, BETA, SampleWith, open_world
from dw_sales.testing.catalog_store import (
    MemoryRecordedConverts,
    MemoryRecordedQuotations,
    MemoryRecordedSenders,
    platform_rules,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
AT = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
GROUP = "group.example"
WHO = uuid.UUID(int=0xA1)


def _customer(code: str, name: str, *contacts: str, domains: tuple[str, ...] = ()) -> Customer:
    """A group company as Bravo's list holds it: its people's addresses on
    the domain the group shares."""
    base = next(c for c in read_records(DATA_DIR / "customers.json", Customer) if c.code == "BRN")
    return Customer.model_validate(
        {
            **base.model_dump(),
            "code": code,
            "name": name,
            "email_domains": domains,
            "contacts": [EmailAddress(address=a).model_dump() for a in contacts],
            "sales_pic": None,
        }
    )


# Two group companies on one domain. Only the first lists the domain as its
# own (as a list exported with one group company's domain filled in does), so
# without the tenant marking it shared the domain would name the first.
GA = _customer("GA", "Group Alpha Co.", "an@group.example", domains=(GROUP,))
GB = _customer("GB", "Group Beta Co.", "binh@group.example", "both@group.example")
GC = _customer("GC", "Group Gamma Co.", "both@group.example")


class Lists:
    """`ApprovedListsPort` holding ``customers`` as ALPHA's approved list."""

    def __init__(self, *customers: Customer) -> None:
        self.customers = customers

    async def approved(self, scope: SalesScope, catalog_list: CatalogList) -> ApprovedList | None:
        if catalog_list is not CatalogList.CUSTOMERS or scope != ALPHA:
            return None
        return ApprovedList.of(catalog_list, uuid.UUID(int=1), AT, self.customers)


def _catalog(*shared: str, ledger: MemoryRecordedSenders | None = None) -> SnapshotSalesCatalog:
    clock = FixedClock(AT)
    return SnapshotSalesCatalog(
        Lists(GA, GB, GC),
        MockSalesCatalog.load(ALPHA),
        MemoryRecordedQuotations(clock),
        MemoryRecordedConverts(clock),
        ledger or MemoryRecordedSenders(clock),
        platform_rules(*shared),
    )


async def _code(
    catalog: SnapshotSalesCatalog, address: str, scope: SalesScope = ALPHA
) -> str | None:
    found = (await catalog.customer_by_sender(scope, address)).data
    return None if found is None else found.code


async def test_two_customers_on_a_shared_domain_are_told_apart_by_address() -> None:
    catalog = _catalog(GROUP)
    assert await _code(catalog, "an@group.example") == "GA"
    assert await _code(catalog, "Binh@Group.example") == "GB"


async def test_a_shared_domain_never_decides_by_itself() -> None:
    assert await _code(_catalog(GROUP), "someone@group.example") is None
    # The marking is what stops it: unmarked, the domain names its customer.
    assert await _code(_catalog(), "someone@group.example") == "GA"


async def test_a_contact_decides_before_any_domain() -> None:
    """A contact of GB's on the domain GA lists is GB's, marked or not."""
    assert await _code(_catalog(), "binh@group.example") == "GB"


async def test_a_ledger_entry_never_overrides_a_contact() -> None:
    ledger = MemoryRecordedSenders(FixedClock(AT))
    # Kept before Bravo listed the address (written past the catalog's check).
    await ledger.learn(ALPHA, "binh@group.example", "GA", by=WHO, message_id="S01")
    catalog = _catalog(GROUP, ledger=ledger)

    assert await _code(catalog, "binh@group.example") == "GB"
    assert not await catalog.learn_sender(ALPHA, "an@group.example", "GB", by=WHO, message_id="S02")
    assert await ledger.sender(ALPHA, "an@group.example") is None
    assert await _code(catalog, "an@group.example") == "GA"


async def test_a_confirmed_address_on_a_shared_domain_is_kept_and_answers() -> None:
    catalog = _catalog(GROUP)
    assert await catalog.learn_sender(
        ALPHA, "New.Buyer@group.example", "GB", by=WHO, message_id="S01"
    )
    assert await _code(catalog, "new.buyer@group.example") == "GB"
    # The address, never its domain.
    assert await _code(catalog, "other@group.example") is None


async def test_an_address_on_a_domain_that_decides_is_not_kept() -> None:
    catalog = _catalog()
    assert not await catalog.learn_sender(
        ALPHA, "someone@group.example", "GB", by=WHO, message_id="S01"
    )
    assert await _code(catalog, "someone@group.example") == "GA"


async def test_an_address_several_customers_list_is_chosen_among_them_only() -> None:
    catalog = _catalog(GROUP)
    assert await _code(catalog, "both@group.example") is None
    assert not await catalog.learn_sender(
        ALPHA, "both@group.example", "GA", by=WHO, message_id="S01"
    )
    assert await _code(catalog, "both@group.example") is None
    assert await catalog.learn_sender(ALPHA, "both@group.example", "GC", by=WHO, message_id="S02")
    assert await _code(catalog, "both@group.example") == "GC"


async def test_a_ledger_entry_outside_the_customers_listing_an_address_decides_nothing() -> None:
    ledger = MemoryRecordedSenders(FixedClock(AT))
    # Kept before Bravo listed the address under GB and GC.
    await ledger.learn(ALPHA, "both@group.example", "GA", by=WHO, message_id="S01")
    assert await _code(_catalog(GROUP, ledger=ledger), "both@group.example") is None


async def test_a_ledger_entry_for_a_customer_no_longer_listed_is_a_persons_not_the_domains() -> (
    None
):
    ledger = MemoryRecordedSenders(FixedClock(AT))
    await ledger.learn(ALPHA, "old.buyer@group.example", "GZ", by=WHO, message_id="S01")
    # Unmarked, the domain would name GA: it is not asked.
    assert await _code(_catalog(ledger=ledger), "old.buyer@group.example") is None


async def test_another_tenants_confirmation_and_contacts_answer_nothing_here() -> None:
    ledger = MemoryRecordedSenders(FixedClock(AT))
    catalog = _catalog(GROUP, ledger=ledger)
    assert await catalog.learn_sender(
        ALPHA, "new.buyer@group.example", "GB", by=WHO, message_id="S01"
    )
    assert await _code(catalog, "new.buyer@group.example", BETA) is None
    assert await _code(catalog, "an@group.example", BETA) is None


async def test_a_shared_domain_is_written_as_a_lowercase_domain_once() -> None:
    document = (await platform_rules().rules(ALPHA)).model_dump(by_alias=True)
    for shared in (["Group.example"], ["group.example", "group.example"], ["not a domain"]):
        with pytest.raises(ValueError, match="shared_mail_domains"):
            OrderRules.model_validate({**document, "shared_mail_domains": shared})


# ----------------------------------------------- through intake, end to end --


def _mail(message_id: str, sender: str) -> dict[str, object]:
    return {
        "message_id": message_id,
        "sender": sender,
        "subject": "PO tháng 11",
        "received_at": "2026-10-28T09:00:00+07:00",
        "body": "Em gửi PO đính kèm, nhờ chị xác nhận giúp em.",
        "authentication": {"spf": "pass", "dkim": "pass", "dmarc": "pass"},
        "attachments": [
            {
                "attachment_id": f"{message_id}-A1",
                "name": "PO.xlsx",
                "media_type": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                "file": str(
                    REPO / "packages/python/dw_sales/src/dw_sales/adapters/mock/attachments"
                    "/M15_TVT-PO-0929-01.xlsx"
                ),
            }
        ],
    }


async def test_a_shared_domain_routes_an_unknown_address_to_a_person_until_confirmed() -> None:
    """The sample tenant marks Brennic's domain shared: its listed contact is
    still Brennic's; an address nobody lists is "customer not known", for a
    person, and once Sales confirms it the next mail from it is Brennic's."""
    unknown, again = (
        _mail("S01", "tran.minh@brennic.example"),
        _mail("S02", "tran.minh@brennic.example"),
    )
    with SampleWith([unknown, again]) as sample:
        world = open_world(REPO, sample, CALLERS, measured=False)
        own = load_tenant_order_rules(sample.data_dir / "policies")
        assert own is not None
        world.store.rule_versions.seed_approved(
            ALPHA.tenant_id.value,
            own.model_copy(
                update={"policy_version": "1.5.9", "shared_mail_domains": ("brennic.example",)}
            ),
        )
        catalog = world.services.sender_customers.catalog
        listed = (await catalog.customer_by_sender(ALPHA, "thu.vo@brennic.example")).data
        assert listed is not None and listed.code == "BRN"

        first, _ = (await world.process_each(AN, ["S01"]))["S01"]
        assert first.reason == "customer_unknown", first

        await world.services.sender_customers.confirm(AN.context(), "S01", "BRN")
        assert await world.drain() == 1
        later, _ = (await world.process_each(AN, ["S02"]))["S02"]
    assert later.customer_code == "BRN" and later.reason != "customer_unknown", later
