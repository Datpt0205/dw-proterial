"""Export the OpenAPI snapshot (contracts/openapi/openapi.json), and the JSON
Schemas a context serves as data (contracts/jsonschema/*.json).

The API app is built with placeholder connection strings — no live services are
contacted; engines/clients are lazy. The snapshot is the contract-test baseline
and the source for the generated TypeScript types.

Usage:
  uv run python scripts/generate_contracts.py          # write snapshot
  uv run python scripts/generate_contracts.py --check  # fail if drifted
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO_ROOT / "contracts" / "openapi" / "openapi.json"
JSONSCHEMA = REPO_ROOT / "contracts" / "jsonschema"


def sales_rule_schemas() -> dict[str, object]:
    """Each Sales rule key's JSON Schema, as `GET /sales/rules/{key}/schema`
    serves it (ticket 40). OpenAPI types that route's `json_schema` as an
    object, so the web's label table is checked against this file instead."""
    from dw_sales.application.rules import OVERRIDABLE, rule_schema

    return {key.value: rule_schema(key) for key in OVERRIDABLE}


# PLUG-IN POINT: a JSON Schema a context serves as a value (not as a route's
# type) and a test outside Python reads. One file per entry.
JSON_SCHEMAS = {"sales_rules.json": sales_rule_schemas}


def _render(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def build_openapi() -> dict[str, object]:
    from dw_api.bootstrap import build_container
    from dw_api.main import create_app
    from dw_api.settings import ApiSettings

    settings = ApiSettings(
        profile="test",
        database_url="postgresql+asyncpg://contract:contract@localhost:5432/contract",
        # The analyst mounts only when a read-only role is configured, so the
        # snapshot needs one spelled out here: reading it from the developer's
        # environment made the contract depend on who ran the command, and a
        # machine with `.env` loaded produced endpoints CI could never generate.
        agent_ro_database_url="postgresql+asyncpg://contract-ro:contract@localhost:5432/contract",
        # Same reasoning for platform provisioning: spell out the provisioner URL
        # so /api/v1/platform/* is always in the snapshot, not dependent on .env.
        provisioner_database_url="postgresql+asyncpg://contract-prov:contract@localhost:5432/contract",
        # And for the Zalo self-link routes, mounted only with both values set.
        zalo_bot_token="contract-zalo-bot-token",
        zalo_link_secret="contract-zalo-link-secret",
        zalo_bot_link="",
        auth_mode="dev",
        dev_secret="contract-snapshot-secret-0123456789",
        s3_endpoint_url="http://localhost:9000",
        s3_access_key="contract",
        s3_secret_key="contract",
        model_provider="mock",
    )
    app = create_app(build_container(settings))
    schema = app.openapi()
    return schema


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify snapshot is current")
    args = parser.parse_args()

    outputs = {SNAPSHOT: _render(build_openapi())}
    outputs |= {JSONSCHEMA / name: _render(build()) for name, build in JSON_SCHEMAS.items()}

    if args.check:
        stale = [
            path
            for path, rendered in outputs.items()
            if not path.exists() or path.read_text(encoding="utf-8") != rendered
        ]
        for path in stale:
            print(
                f"{path.relative_to(REPO_ROOT)} is stale — run `make generate-contracts`",
                file=sys.stderr,
            )
        if stale:
            return 1
        print("OpenAPI snapshot and JSON Schemas are current.")
        return 0

    for path, rendered in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        print(f"Wrote {path.relative_to(REPO_ROOT)} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
