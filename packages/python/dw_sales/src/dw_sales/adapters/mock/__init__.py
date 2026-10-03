"""Mock master data and mailbox: fictional fixtures behind the real ports.

`MockSalesCatalog` and `MockInbox` implement `SalesCatalogPort` and
`InboxPort` until ERP and Microsoft 365 adapters replace them. What each mock
email is meant to exercise is listed in `README.md` beside this file.
"""

from dw_sales.adapters.mock.catalog import MockSalesCatalog
from dw_sales.adapters.mock.inbox import MockInbox

__all__ = ["MockInbox", "MockSalesCatalog"]
