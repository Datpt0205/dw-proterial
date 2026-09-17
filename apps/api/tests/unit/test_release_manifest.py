"""Release manifest generation is deterministic and complete."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_script():  # scripts/ is not a package; load by path
    spec = importlib.util.spec_from_file_location(
        "release_manifest", REPO_ROOT / "scripts" / "release_manifest.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_manifest"] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_contains_every_required_section() -> None:
    script = _load_script()
    manifest = script.build_manifest()
    for key in (
        "platform_version",
        "git_sha",
        "api_version",
        "workers",
        "prompt_bundles",
        "tool_specs",
        "toolsets",
        "policies",
        "knowledge_index_version",
        "memory_policy_version",
        "eval_datasets",
    ):
        assert key in manifest, f"manifest missing {key}"
    # Platform artifacts, which exist with no bounded context installed. A
    # context adds its own worker/prompt/policy assertions beside these; naming
    # one here would make this test fail on a checkout that does not host it.
    assert {p["prompt_id"] for p in manifest["prompt_bundles"]} >= {"platform.untrusted_demo"}
    # Every worker's toolset_version must resolve to a pin file, or a run records
    # a toolset nobody can reconstruct.
    pinned = {(t["toolset_id"], t["version"]) for t in manifest["toolsets"]}
    assert {(w["worker_id"], w["toolset_version"]) for w in manifest["workers"]} <= pinned
    assert {d["dataset_id"] for d in manifest["eval_datasets"]} >= {"platform_smoke"}


def test_manifest_ref_is_stable_and_ignores_git_sha() -> None:
    script = _load_script()
    manifest = script.build_manifest()
    ref = script.manifest_ref(manifest)
    assert ref.startswith("sha256:") and len(ref) == 7 + 64
    assert ref == script.manifest_ref({**manifest, "git_sha": "different"})
    changed = {**manifest, "knowledge_index_version": "changed"}
    assert ref != script.manifest_ref(changed)
