# Tool specs

One file per tool version, `<namespace>.<name>@<semver>.yaml`. The spec is the
**policy** — scopes, side-effect level, whether it needs approval, its
idempotency and timeout — and it is deliberately separate from the code that
implements the tool: the executor reads the spec, never the factory's opinion of
itself.

This directory ships empty. Every tool belongs to a bounded context, and the
platform installs none of its own, so a spec here with no factory registered
would be a description of something that does not exist — and the model would be
told it could call it.

A context adds its specs here in the same change that registers its factories on
`RuntimeSeam.tools`, and pins them in a toolset under `configs/toolsets/`.
