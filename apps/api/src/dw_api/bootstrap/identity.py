"""Who the caller is: token verification.

Two verifiers, chosen by ``auth_mode`` rather than by what happens to be
configured, so a deployment cannot fall back to the development issuer by
forgetting a variable — ``validate_for_profile`` refuses that combination before
this runs.
"""

from __future__ import annotations

from dw_api.settings import ApiSettings
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.adapters.identity.keycloak import KeycloakTokenVerifier
from dw_platform.application.ports import TokenVerifierPort


def build_token_verifier(settings: ApiSettings) -> TokenVerifierPort | None:
    if settings.auth_mode == "oidc":
        assert settings.oidc_issuer_url is not None  # validate_for_profile enforced
        return KeycloakTokenVerifier(
            settings.oidc_issuer_url, settings.oidc_audience, settings.oidc_jwks_url
        )
    if settings.dev_secret:
        return DevTokenVerifier(settings.dev_secret)
    # Auth stays off until a secret is configured. Only reachable in `local`:
    # every other profile requires oidc.
    return None
