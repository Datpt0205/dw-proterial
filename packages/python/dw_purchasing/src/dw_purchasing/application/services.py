"""What the Purchasing router serves, bundled by the composition root."""

from __future__ import annotations

from dataclasses import dataclass

from dw_purchasing.application.approvals import RequestApprovals
from dw_purchasing.application.automation import SwitchesService
from dw_purchasing.application.intake import PurchaseRequests
from dw_purchasing.application.master_data import MasterDataService
from dw_purchasing.application.orders import PurchaseOrders
from dw_purchasing.application.requesters import RequesterDesk
from dw_purchasing.application.rfq_mail import RfqMailService
from dw_purchasing.application.rule_drafting import RuleWordsDesk
from dw_purchasing.application.rules import PurchasingRulesService
from dw_purchasing.application.sourcing import SupplierSourcing


@dataclass(frozen=True)
class PurchasingServices:
    requests: PurchaseRequests
    approvals: RequestApprovals
    sourcing: SupplierSourcing
    orders: PurchaseOrders
    rules: PurchasingRulesService
    switches: SwitchesService
    requester: RequesterDesk
    words: RuleWordsDesk
    master_data: MasterDataService
    rfq_mails: RfqMailService
