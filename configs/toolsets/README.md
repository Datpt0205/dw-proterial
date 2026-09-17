# Toolsets

One file per worker version: the exact set of tool versions a worker offers the
model in a turn, pinned by version. Separate from `configs/tools/` because a
superseded spec stays loadable — history a run can be replayed against — while
only what a toolset pins is built into a tool the model can see.

Empty for the same reason `configs/tools/` is: a toolset pins tools, and the
platform registers none. A pin naming a tool nobody registered fails at startup
rather than when a model first reaches for it, which is the behaviour you want.
