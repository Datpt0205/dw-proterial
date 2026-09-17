# brandkit — vendored engine

Third-party code. **Do not edit anything under `brandkit/`.** Lint and format
skip this tree (`extend-exclude` in the root `pyproject.toml`) so a diff here is
always a re-vendor, never a local patch. A change we need goes upstream as a PR
and comes back as a new pin.

| | |
|---|---|
| Upstream | <https://github.com/ferdinandobons/brand-docs> |
| Version | `v0.10.1` |
| Commit | `97a6e384cb0664cd44ba8113c0b80c9761700670` |
| License | MIT — see [LICENSE](LICENSE) and [NOTICE](NOTICE) |
| Vendored from | `scripts/brandkit/` of the upstream tree |

## Why vendored rather than a dependency

Upstream ships as a Claude Code / Codex *plugin*, not a package on PyPI, so
there is nothing to pin in `uv.lock`. Copying the engine at one tag is the only
way to get a reproducible build of the sandbox image.

## Why only `scripts/brandkit/`

That directory is the engine: the OOXML resolver, the profile schema, the QA
gate and the CLI. The rest of the upstream tree is the agent-facing plugin
(skills, commands, docs, test corpus, example templates) which this repo
replaces with its own — see `configs/skills/sales_chat/`.

## Runtime dependencies

`python-docx`, `python-pptx`, `openpyxl`, `lxml`, `Pillow`, plus the external
binaries `soffice` and `pdftoppm` for visual QA. They are installed in the
sandbox image, `infra/docker/docgen.Dockerfile`.

## Re-vendoring

```sh
scripts/vendor_brandkit.sh v0.10.2
```

Then run the sandbox image tests: the engine is exercised through
`brandkit doctor` and a generate round-trip, which is what catches an upstream
break.
