# Toolsets

One file per worker version: the exact set of tool versions a worker offers the
model in a turn, pinned by version. Separate from `configs/tools/` because a
superseded spec stays loadable — history a run can be replayed against — while
only what a toolset pins is built into a tool the model can see.

A toolset pins a context's tools; the platform registers none of its own. A
pin naming a tool nobody registered fails at startup rather than when a model
first reaches for it, which is the behaviour you want. `sales-dw1` is DW1's
(`configs/workers/sales.yaml` pins it): read-only tools, side effect `none`;
the skill loader it pins since 1.1.0 is offered only to a turn served skills
(`AgentTurnKit.turn`).
