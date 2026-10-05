"""The Sales policies in ``configs/policies``, each validated by its own model.

The platform layer of the per-tenant lookup: what ships in the repository. A
file's name and its content both state the version, and the release manifest
records the content's: a name that disagrees is a file somebody edited
without bumping one of the two, refused when it loads.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from dw_sales.application.quotation import QuoteRules
from dw_sales.domain.kpi import SalesKpi
from dw_sales.domain.pricing import SalesPricing


def load_policy[T: BaseModel](path: Path, model: type[T]) -> T:
    """``path`` validated by ``model``, refused when named for another version."""
    loaded = model.model_validate(yaml.safe_load(path.read_bytes()))
    version = getattr(loaded, "version", None)
    if not isinstance(version, str) or path.name != f"{version}.yaml":
        raise ValueError(f"{path.name} holds {version}")
    return loaded


def load_quote_rules(path: Path) -> QuoteRules:
    return load_policy(path, QuoteRules)


def load_pricing(path: Path) -> SalesPricing:
    return load_policy(path, SalesPricing)


def load_kpi(path: Path) -> SalesKpi:
    return load_policy(path, SalesKpi)
