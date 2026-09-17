"""An eval must grade the prompt that ships, not one it used to.

This has now gone wrong three times in this repo, each time silently. A prompt
gets a new version; the fixture that renders it keeps naming the old one; the
guardrail suite goes green for a file no request has touched in weeks. Nothing
fails, because the superseded prompt is still on disk and still renders — being
retired is not the same as being deleted.

The invariant is narrow on purpose: only the CURRENT dataset of each domain is
held to it. Older datasets are history and are allowed to name the prompt they
were written against; that is what makes them replayable.
"""

from __future__ import annotations

import json
import pathlib

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
PROMPTS = REPO_ROOT / "configs" / "prompts"
DATASETS = REPO_ROOT / "evals" / "datasets"


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _newest_prompt_versions() -> dict[str, str]:
    """``<dir>.<name>`` -> the highest version of that prompt on disk.

    The directory is the prompt's owning worker and the stem before ``@`` is its
    id, which together are exactly the ``prompt_id`` a fixture names.
    """
    newest: dict[str, str] = {}
    for path in PROMPTS.rglob("*.yaml"):
        name, _, version = path.stem.partition("@")
        prompt_id = f"{path.parent.name}.{name}"
        if prompt_id not in newest or _version_key(version) > _version_key(newest[prompt_id]):
            newest[prompt_id] = version
    return newest


def _current_datasets() -> list[pathlib.Path]:
    newest: dict[str, tuple[tuple[int, ...], pathlib.Path]] = {}
    for path in DATASETS.glob("*.json"):
        dataset_id, _, version = path.stem.partition("@")
        key = _version_key(version)
        if dataset_id not in newest or key > newest[dataset_id][0]:
            newest[dataset_id] = (key, path)
    return [path for _, path in sorted(newest.values(), key=lambda item: item[1].name)]


def _pinned_prompts() -> list[tuple[str, str, str]]:
    """(dataset, prompt_id, pinned version) for every case of every live dataset."""
    pins = []
    for dataset in _current_datasets():
        cases = json.loads(dataset.read_text(encoding="utf-8")).get("cases", ())
        for case in cases:
            reference = case.get("input_ref")
            if not reference:
                continue
            fixture = json.loads((REPO_ROOT / reference).read_text(encoding="utf-8"))
            prompt_id = fixture.get("prompt_id")
            if not prompt_id:
                continue
            pinned = fixture.get("prompt_version") or fixture.get("version")
            pins.append((dataset.name, prompt_id, str(pinned)))
    return pins


def test_every_live_eval_grades_the_newest_prompt() -> None:
    newest = _newest_prompt_versions()
    stale = [
        f"{dataset} pins {prompt_id}@{pinned}, newest is {newest[prompt_id]}"
        for dataset, prompt_id, pinned in _pinned_prompts()
        if prompt_id in newest and pinned != newest[prompt_id]
    ]
    assert not stale, "eval fixtures are grading superseded prompts: " + "; ".join(stale)


def test_the_pins_name_prompts_that_exist() -> None:
    """A typo in a prompt id would make the check above vacuously true."""
    newest = _newest_prompt_versions()
    unknown = [
        f"{dataset} names unknown prompt {prompt_id}"
        for dataset, prompt_id, _ in _pinned_prompts()
        if prompt_id not in newest
    ]
    assert not unknown, "; ".join(unknown)


def test_something_is_actually_pinned() -> None:
    """Guards the guard: if fixtures stop carrying prompt_id, both tests above
    pass on an empty list and the suite quietly stops covering anything."""
    assert _pinned_prompts()
