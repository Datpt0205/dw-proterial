"""Run evaluation datasets and write versioned reports.

Usage:
    uv run python scripts/run_evals.py --smoke              # all datasets
    uv run python scripts/run_evals.py --dataset evals/datasets/platform@1.2.0.json

    # The live lane, outside CI: a dataset's model steps against a real model
    # (the `onprem` profile: DW_ONPREM_MODEL_BASE_URL, e.g. a local Ollama),
    # reporting accuracy, the share routed to a person and latency. --record
    # writes the answers the smoke replays, so CI scores those same readings.
    uv run python scripts/run_evals.py --live onprem --record
        --dataset evals/datasets/sales_descriptions@1.0.0.json

Exit code is non-zero when any case fails or a dataset lacks full security
coverage (prompt injection, cross-tenant attack, missing evidence).

This script is the eval composition root: `grader_table` is the one place the
grader table is built, from the platform's graders plus each bounded context's,
the same way `apps/api/.../bootstrap/wiring.py` and `apps/worker/.../main.py`
are where a context joins the API and the worker. `dw_evals` imports no
context; a context registers its graders here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dw_evals.graders import Grader

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASETS_DIR = REPO_ROOT / "evals" / "datasets"
REPORTS_DIR = REPO_ROOT / "evals" / "reports"


def grader_table() -> dict[str, Grader]:
    """Every grader a dataset may name. Two tables claiming one name stop the
    run (`merge_graders` raises, naming it)."""
    from dw_evals.graders import GRADERS, merge_graders

    tables = [GRADERS]
    # ---- BOUNDED CONTEXT GRADERS REGISTER HERE ----------------------------
    from dw_sales.evals import GRADERS as SALES_GRADERS

    tables.append(SALES_GRADERS)
    return merge_graders(*tables)


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="run every dataset in evals/datasets")
    parser.add_argument("--dataset", type=Path, help="run a single dataset file")
    parser.add_argument(
        "--live",
        metavar="PROFILE",
        help="run the dataset's model steps on PROFILE's live model (never in CI)",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="with --live: write the answers the smoke replays",
    )
    args = parser.parse_args()
    if args.live and not args.dataset:
        parser.error("--live runs one dataset: pass --dataset <file>")
    if args.record and not args.live:
        parser.error("--record needs --live")

    from dw_evals.runner import load_dataset, run_dataset, write_report

    if args.dataset:
        paths = [args.dataset]
    else:
        paths = sorted(DATASETS_DIR.glob("*.json"))
        if not args.smoke:
            parser.error("pass --smoke or --dataset <file>")
    if not paths:
        print("ERROR: no datasets found under evals/datasets", file=sys.stderr)
        return 1

    graders = grader_table()
    live_model = live_model_for(args.live) if args.live else None
    exit_code = 0
    for path in paths:
        dataset = load_dataset(path)
        report = run_dataset(dataset, REPO_ROOT, graders, live_model=live_model)
        report_path = write_report(
            report, REPORTS_DIR / f"live-{args.live}" if args.live else REPORTS_DIR
        )
        status = "PASS" if report.ok else "FAIL"
        print(
            f"[{status}] {report.dataset_id}@{report.dataset_version} "
            f"({report.worker_id}): {report.passed}/{report.total} cases, "
            f"security coverage {'ok' if report.security_coverage_ok else 'MISSING'} "
            f"→ {report_path.relative_to(REPO_ROOT)}"
        )
        for result in report.results:
            if not result.passed:
                print(f"    ✗ {result.case_id} [{result.category}] {result.details}")
        if not report.ok:
            exit_code = 1
        if live_model is not None:
            for result in report.results:
                print(f"    {result.case_id}: {_summary(result.details)}")
    if args.record and live_model is not None:
        print(f"recorded {record_answers(live_model)} answers")
    return exit_code


# ---- THE LIVE LANE: a real model, outside CI -----------------------------
# Composed here, like the graders: the eval composition root is where a
# context's model step meets a model. Local development only: the endpoint
# guard admits localhost because this is not a deployed profile.

_CASES = REPO_ROOT / "evals" / "fixtures" / "cases"
RECORDED = _CASES / "sales_descriptions_recorded.json"
# Where each model step's recorded answers live, by prompt id: the files the
# smoke replays (`dw_sales.evals.recorded`).
RECORDED_BY_PROMPT = {
    "sales.message_intent": _CASES / "sales_intent_recorded.json",
    "sales.rfq_extraction": _CASES / "sales_rfq_recorded.json",
}


def live_model_for(profile: str) -> object:
    import os

    from dw_agent_runtime.adapters.model_stack import ModelProviderConfig, build_model_adapters
    from dw_agent_runtime.model.gateway import InMemoryUsageRecorder, RoutingModelGateway
    from dw_agent_runtime.model.profiles import ModelProfileRegistry
    from dw_agent_runtime.model.prompts import PromptRegistry
    from dw_sales.adapters.assembly import interpretation_for
    from dw_sales.evals.recorded import Observed

    profiles = ModelProfileRegistry()
    profiles.load_directory(REPO_ROOT / "configs" / "models")
    prompts = PromptRegistry()
    prompts.load_directory(REPO_ROOT / "configs" / "prompts")
    config = ModelProviderConfig(
        provider="live-eval",
        model_profile=profile,
        profile="local",
        is_deployed=False,
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        openai_base_url=os.environ.get("OPENAI_BASE_URL") or None,
        onprem_base_url=os.environ.get("DW_ONPREM_MODEL_BASE_URL") or None,
    )
    gateway = RoutingModelGateway(
        profiles=profiles,
        prompts=prompts,
        adapters=build_model_adapters(config, mock_fixtures_dir=REPO_ROOT / "evals"),
        usage_recorder=InMemoryUsageRecorder(),
        default_profile=profiles.resolve(profile).profile_id,
    )
    return Observed(interpretation_for(gateway, REPO_ROOT / "configs", profile))


def record_answers(model: object) -> int:
    import json

    count = 0
    for prompt_id, answers in getattr(model, "recorded", {}).items():
        path = RECORDED_BY_PROMPT[prompt_id]
        held = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        held["_comment"] = (
            f"The local model's answers (onprem profile) to {prompt_id}, by answer key (the "
            "prompt and its exact inputs, hashed), recorded by `run_evals.py --live onprem "
            "--record`; the smoke replays them, so CI scores the same readings through the same "
            "code without a model. null: the call gave no usable answer. Fictional text."
        )
        held["answers"] = dict(sorted({**held.get("answers", {}), **answers}.items()))
        path.write_bytes((json.dumps(held, ensure_ascii=False, indent=2) + chr(10)).encode("utf-8"))
        count += len(answers)
    answers = dict(getattr(model, "answers", {}))
    if not answers:
        return count
    held = json.loads(RECORDED.read_text(encoding="utf-8")) if RECORDED.exists() else {}
    merged = {**held.get("answers", {}), **answers}
    held["_comment"] = (
        "The local model's answers (onprem profile) to ticket 28's descriptions, recorded by "
        "`run_evals.py --live onprem --record`; the smoke replays them, so CI scores the "
        "same readings through the same verification without a model. Fictional text."
    )
    held["answers"] = dict(sorted(merged.items()))
    text = json.dumps(held, ensure_ascii=False, indent=2) + chr(10)
    RECORDED.write_bytes(text.encode("utf-8"))
    return count + len(answers)


def _summary(details: dict[str, object]) -> str:
    keys = (
        "all",
        "vi_en",
        "by_language",
        "latency",
        "meets_proposed_bar",
        "meets_proposed_bar_vi_en",
        "seen",
        "reason",
    )
    import json

    return json.dumps({k: details[k] for k in keys if k in details}, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
