"""No token signs in as a service account (sales ticket 16).

DW1's account is a platform user whose subject no identity provider should
ever issue; the verifier the API is built with refuses that subject, whichever
issuer the deployment uses, so no request, bootstrap, support or provisioning
path resolves it.
"""

from __future__ import annotations

import uuid

import pytest

from dw_api.bootstrap.identity import build_token_verifier
from dw_api.settings import ApiSettings
from dw_kernel.errors import PermissionDeniedError
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.application.identity import ServiceSubjectsRefused
from dw_sales.application.inbox_lane import dw1_subject

pytestmark = pytest.mark.unit

SECRET = "unit-test-secret-0123456789abcdef"


async def test_the_built_verifier_refuses_dw1s_subject_and_passes_a_persons() -> None:
    verifier = build_token_verifier(ApiSettings(profile="test", dev_secret=SECRET))
    assert verifier is not None
    issuer = DevTokenVerifier(SECRET)

    with pytest.raises(PermissionDeniedError):
        await verifier.verify(issuer.issue(dw1_subject(uuid.uuid4())))
    assert (await verifier.verify(issuer.issue("dev|an.nguyen"))).subject == "dev|an.nguyen"


def test_the_oidc_verifier_is_wrapped_the_same_way() -> None:
    settings = ApiSettings(
        profile="test", auth_mode="oidc", oidc_issuer_url="https://issuer.test/realms/dw"
    )

    assert isinstance(build_token_verifier(settings), ServiceSubjectsRefused)
