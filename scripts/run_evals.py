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

    # The live lane, attested for one tenant (dw_sales ADR 0005, addendum of
    # 2026-10-23): the dataset's model step measured on the profile's model and
    # recorded for the tenant as the lane `sales_model_attest`, as dw_app
    # (DW_WORKER_DATABASE_URL) under the tenant's RLS, audited. A tenant turns
    # a step on, and DW1 uses it, only once its latest such measurement passed.
    uv run python scripts/run_evals.py --live onprem --attest
        --tenant <uuid> --workspace <uuid>
        --dataset evals/datasets/sales_intent@1.0.0.json

Exit code is non-zero when any case fails or a dataset lacks full security
coverage (prompt injection, cross-tenant attack, missing evidence). A live
run also fails when the model read nothing (no call gave a usable answer,
`live_shortfalls`): its cases grade the guards, which hold just as well when
every call times out. So `--live` is for a dataset with a model step: one
without reads nothing and fails as such. A golden case's bar
(`dw_sales.application.model_readiness.BARS`) is reported in its summary
line; it is enforced where a step is turned on and used, from what `--attest`
records, never from a report file.

This script is the eval composition root: `grader_table` is the one place the
grader table is built, from the platform's graders plus each bounded context's,
the same way `apps/api/.../bootstrap/wiring.py` and `apps/worker/.../main.py`
are where a context joins the API and the worker. `dw_evals` imports no
context; a context registers its graders here.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
        help=(
            "run the dataset's model steps on PROFILE's live model (never in CI); "
            "a dataset with no model step reads nothing and fails"
        ),
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="with --live: write the answers the smoke replays",
    )
    parser.add_argument(
        "--attest",
        action="store_true",
        help="with --live: record the step's measurement for --tenant, in --workspace",
    )
    parser.add_argument("--tenant", type=uuid.UUID, help="with --attest: the tenant measured")
    parser.add_argument(
        "--workspace", type=uuid.UUID, help="with --attest: the workspace it is recorded in"
    )
    args = parser.parse_args()
    if args.live and not args.dataset:
        parser.error("--live runs one dataset: pass --dataset <file>")
    if args.record and not args.live:
        parser.error("--record needs --live")
    if args.attest and not (args.live and args.tenant and args.workspace):
        parser.error("--attest needs --live, --tenant and --workspace")
    if (args.tenant or args.workspace) and not args.attest:
        parser.error("--tenant and --workspace go with --attest")

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
        shortfalls = live_shortfalls(live_model) if live_model is not None else []
        status = "PASS" if report.ok and not shortfalls else "FAIL"
        print(
            f"[{status}] {report.dataset_id}@{report.dataset_version} "
            f"({report.worker_id}): {report.passed}/{report.total} cases, "
            f"security coverage {'ok' if report.security_coverage_ok else 'MISSING'} "
            f"→ {report_path.relative_to(REPO_ROOT)}"
        )
        for result in report.results:
            if not result.passed:
                print(f"    ✗ {result.case_id} [{result.category}] {result.details}")
        for shortfall in shortfalls:
            print(f"    ✗ live: {shortfall}")
        if not report.ok or shortfalls:
            exit_code = 1
        if live_model is not None:
            for result in report.results:
                print(f"    {result.case_id}: {_summary(result.details)}")
        if args.attest:
            if shortfalls:
                # A run that read nothing measured nothing: no row either way.
                print("    ✗ attest: nothing was read, so nothing is recorded")
                continue
            print(f"    {attest(report, args.live, args.tenant, args.workspace)}")
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
    "sales.reply_intent": _CASES / "sales_reply_recorded.json",
    "sales.request_handoff": _CASES / "sales_handoff_recorded.json",
    "sales.po_layout_proposal": _CASES / "sales_layout_recorded.json",
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


def live_shortfalls(model: object) -> list[str]:
    """Why a live run fails whatever its cases say: the model read nothing
    (``model`` is the lane's `Observed`: no call, or no call that gave a usable
    answer)."""
    calls, answered = len(getattr(model, "calls", ())), getattr(model, "answered", 0)
    if not answered:
        return [f"nothing was read: {calls} model calls, none gave a usable answer"]
    return []


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


def attest(report: Any, profile: str, tenant: uuid.UUID, workspace: uuid.UUID) -> str:
    """Records the live run's measurement of its dataset's step for one
    tenant: the golden case's verdict on the bar (`model_readiness.BARS`),
    passing only where every case of the run passed too, on the model
    ``profile`` routed the run to (the platform layer the eval gateway
    loads). Written as the lane `sales_model_attest`, as dw_app under the
    tenant's RLS, with its audit event; refused for a role that bypasses RLS."""
    import asyncio
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from dw_kernel.ids import TenantId, WorkspaceId
    from dw_kernel.ports import SystemClock, Uuid7Generator
    from dw_platform.adapters.persistence.repositories import SqlAuditRepository
    from dw_sales.adapters.assembly import step_model
    from dw_sales.adapters.persistence.measurements import SqlMeasurementLog
    from dw_sales.application.model_readiness import BARS, ModelAttestation, step_measured_by
    from dw_sales.application.ports import SalesScope

    step = step_measured_by(report.dataset_id)
    if step is None:
        raise SystemExit(f"--attest: {report.dataset_id} measures no model step")
    golden = next(r for r in report.results if r.grader == BARS[step].grader)
    verdict = golden.details["bar"]
    database_url = os.environ.get("DW_WORKER_DATABASE_URL")
    if not database_url:
        raise SystemExit("--attest: DW_WORKER_DATABASE_URL is not set (source .env)")
    # What the run was routed to: the platform layer, as `live_model_for` loads it.
    model = step_model(REPO_ROOT / "configs", profile).model_for(tenant)

    async def record() -> object:
        engine = create_async_engine(database_url, poolclass=NullPool)
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with sessions() as session:
                bypasses = await session.scalar(
                    text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
                )
            if bypasses is not False:
                raise SystemExit("--attest: refusing a database role that bypasses RLS")
            attestation = ModelAttestation(
                SqlMeasurementLog(sessions, audit=SqlAuditRepository),
                SystemClock(),
                Uuid7Generator(),
            )
            return await attestation.attest(
                SalesScope(TenantId(tenant), WorkspaceId(workspace)),
                step,
                model=model,
                value=float(verdict["value"]),
                held=bool(verdict["passed"]) and report.ok,
                dataset=f"{report.dataset_id}@{report.dataset_version}",
            )
        finally:
            await engine.dispose()

    return f"attested: {asyncio.run(record())!r}"


def _summary(details: dict[str, object]) -> str:
    keys = (
        "all",
        "vi_en",
        "by_language",
        "latency",
        "bar",
        "seen",
        "reason",
    )
    import json

    return json.dumps({k: details[k] for k in keys if k in details}, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
