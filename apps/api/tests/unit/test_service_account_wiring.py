"""What the API's composition root registers with provisioning.

The provisioning service's own test proves a registered service account is
created with each tenant. This proves Sales registers DW1's at the seam: without
it, deleting that one line from `bootstrap/wiring.py` would leave every other
test green while a production tenant got no account and its mailbox lane did
nothing (sales ticket 16).
"""

import pytest

from dw_api.bootstrap import build_container
from dw_api.settings import ApiSettings
from dw_sales.application.inbox_lane import DW1_SERVICE_ACCOUNT

pytestmark = pytest.mark.unit


def test_every_new_tenant_gets_dw1s_service_account() -> None:
    # As `scripts/generate_contracts.py` builds it: engines are lazy, so a
    # placeholder database is enough to compose the container.
    container = build_container(
        ApiSettings(
            profile="test",
            database_url="postgresql+asyncpg://wiring:wiring@localhost:5432/wiring",
            provisioner_database_url="postgresql+asyncpg://prov:prov@localhost:5432/wiring",
            dev_secret="wiring-test-secret-0123456789abcdef",
            s3_endpoint_url="http://localhost:9000",
            s3_access_key="wiring",
            s3_secret_key="wiring",
            model_provider="mock",
        )
    )

    assert container.provisioning is not None
    assert list(container.provisioning.service_accounts) == [DW1_SERVICE_ACCOUNT]
