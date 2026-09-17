"""The autonomy levels a Digital Worker can run at.

In the kernel, and nowhere else, because two layers must agree on them and
neither may import the other: the agent runtime decides what each level permits,
and the platform stores the ceiling a tenant sets. A second copy of this list in
either one is how a tenant comes to be offered a level the runtime has never
heard of — or refused one it would have honoured.

The database holds the same five values as a CHECK constraint, and that is the
guarantee; this is the list the code reads.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

AutonomyLevel = Literal["A0", "A1", "A2", "A3", "A4"]

# Lowest to highest. The order IS the meaning: a later level may do everything an
# earlier one may, and more.
AUTONOMY_LEVELS: Final[tuple[AutonomyLevel, ...]] = get_args(AutonomyLevel)

# What a tenant with no ceiling of its own is held to: nothing beyond what the
# worker was built for. Not a permission — the worker's declared level still
# caps every run — only the absence of an extra restriction.
NO_TENANT_CEILING: Final[AutonomyLevel] = "A4"

# The level to assume when a ceiling should exist and cannot be read. The most
# restrictive, because refusing a legitimate action is recoverable and taking an
# illegitimate one is not.
FAIL_CLOSED_LEVEL: Final[AutonomyLevel] = "A0"


def is_autonomy_level(value: object) -> bool:
    return value in AUTONOMY_LEVELS
