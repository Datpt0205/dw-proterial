"""Release manifest generation is deterministic and complete."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_script() -> Any:  # scripts/ is not a package; load by path
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
        "model_profiles",
        "knowledge_index_version",
        "memory_policy_version",
        # A run stamps this on its own row and the policy refuses to decide for a
        # run stamped under a version this process does not have. That makes it a
        # versioned artifact whether or not it lives in a YAML file, so a release
        # that changes it has to be identifiable afterwards.
        "approval_policy_version",
        "eval_datasets",
    ):
        assert key in manifest, f"manifest missing {key}"
    # The version a run is actually stamped with, not a second copy of the string.
    from dw_agent_runtime.autonomy import AUTONOMY_POLICY_VERSION

    assert manifest["approval_policy_version"] == AUTONOMY_POLICY_VERSION
    # Platform artifacts, which exist with no bounded context installed. A
    # context adds its own worker/prompt/policy assertions beside these; naming
    # one here would make this test fail on a checkout that does not host it.
    assert {p["prompt_id"] for p in manifest["prompt_bundles"]} >= {"platform.untrusted_demo"}
    # Every worker that DECLARES a toolset_version must have it resolve to a
    # pin file, or a run records a toolset nobody can reconstruct. `None` is
    # the honest value for a worker that calls no tool at all (a plain graph,
    # not an agent loop) — see `WorkerDefinition.toolset_version`'s own
    # docstring — and is exempt from this check rather than required to
    # resolve to nothing.
    pinned = {(t["toolset_id"], t["version"]) for t in manifest["toolsets"]}
    assert {
        (w["worker_id"], w["toolset_version"])
        for w in manifest["workers"]
        if w["toolset_version"] is not None
    } <= pinned
    # Same for the prompt an agent-loop worker pins: a run's spend is recorded
    # under it, so it must be a prompt this release ships.
    bundled = {(p["prompt_id"], p["version"]) for p in manifest["prompt_bundles"]}
    assert {
        (w["agent_prompt_id"], w["agent_prompt_version"])
        for w in manifest["workers"]
        if w["agent_prompt_id"] is not None
    } <= bundled
    assert {d["dataset_id"] for d in manifest["eval_datasets"]} >= {"platform_smoke"}


def test_manifest_ref_is_stable_and_ignores_git_sha() -> None:
    script = _load_script()
    manifest = script.build_manifest()
    ref = script.manifest_ref(manifest)
    assert ref.startswith("sha256:") and len(ref) == 7 + 64
    assert ref == script.manifest_ref({**manifest, "git_sha": "different"})
    changed = {**manifest, "knowledge_index_version": "changed"}
    assert ref != script.manifest_ref(changed)


def test_an_eval_dataset_pins_the_files_its_cases_name() -> None:
    """The dataset file alone left its fixtures and expectations unpinned:
    editing an expectation changed a grade and moved no ref."""
    script = _load_script()
    manifest = script.build_manifest()
    [smoke] = [d for d in manifest["eval_datasets"] if d["dataset_id"] == "platform_smoke"]
    dataset = next(
        script.json.loads(path.read_text(encoding="utf-8"))
        for path in (REPO_ROOT / "evals" / "datasets").glob("*.json")
        if script.json.loads(path.read_text(encoding="utf-8"))["dataset_id"] == "platform_smoke"
    )
    named = {ref for case in dataset["cases"] for ref in (case["input_ref"], case["expected_ref"])}

    assert named <= {f["path"] for f in smoke["files"]}
    assert all(len(f["checksum"]) == 64 for f in smoke["files"])


def _fake_repo(tmp_path: Path, truth: str) -> Path:
    (tmp_path / "evals" / "datasets").mkdir(parents=True)
    (tmp_path / "evals" / "expected").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "truth.json").write_text(truth, encoding="utf-8")
    (tmp_path / "evals" / "expected" / "case.json").write_text(
        '{"truth": "data/truth.json", "note": "graded against data/truth.json"}',
        encoding="utf-8",
    )
    (tmp_path / "evals" / "datasets" / "demo@1.0.0.json").write_text(
        '{"dataset_id": "demo", "dataset_version": "1.0.0",'
        ' "cases": [{"expected_ref": "evals/expected/case.json"}]}',
        encoding="utf-8",
    )
    return tmp_path


def test_a_truth_file_named_by_an_expectation_is_pinned_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _load_script()
    monkeypatch.setattr(script, "REPO_ROOT", _fake_repo(tmp_path, '{"price": 1}'))

    [before] = script._eval_datasets()
    (tmp_path / "data" / "truth.json").write_text('{"price": 2}', encoding="utf-8")
    [after] = script._eval_datasets()

    assert [f["path"] for f in before["files"]] == ["data/truth.json", "evals/expected/case.json"]
    # The dataset file did not change; only the truth two hops away did.
    assert before["checksum"] == after["checksum"]
    assert before["files"] != after["files"]


def test_a_named_file_that_does_not_exist_stops_the_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _load_script()
    monkeypatch.setattr(script, "REPO_ROOT", _fake_repo(tmp_path, "{}"))
    (tmp_path / "data" / "truth.json").unlink()

    with pytest.raises(SystemExit, match=r"names data/truth.json"):
        script._eval_datasets()


def test_every_model_profile_is_pinned_by_content() -> None:
    """The profile decides which provider reads a customer's text and what a
    run costs; editing one has to move the ref like editing a prompt does."""
    script = _load_script()
    manifest = script.build_manifest()
    shipped = {
        script.yaml.safe_load(path.read_text(encoding="utf-8"))["profile_id"]: path
        for path in (REPO_ROOT / "configs" / "models").glob("*.yaml")
    }

    pins = {p["profile_id"]: p for p in manifest["model_profiles"]}
    assert set(pins) == set(shipped)
    for profile_id, path in shipped.items():
        assert pins[profile_id]["checksum"] == script._checksum(path)
