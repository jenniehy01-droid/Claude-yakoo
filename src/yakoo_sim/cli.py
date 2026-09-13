"""CLI 진입점.

사용 예시는 README.md 참고. 모든 손익 숫자는 이 CLI가 호출하는
Python 계산 함수(calculator.py, scenarios.py, pilot_update.py)의
실행 결과만 사용하며, report.py는 이미 저장된 JSON을 읽어 서식만
입힌다 (새로운 손익 수치를 만들어내지 않는다).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .calculator import compute_all_scenarios
from .io_loader import DummyFileInputSource, sha256_of_file
from .models import Assumption
from .pilot_update import (
    apply_rate_updates,
    compute_conversion_rates,
    compute_repeat_purchase_rates,
    ingest_conversion_file,
    ingest_repeat_file,
    load_ledger,
    save_ledger,
)
from .scenarios import rank_scenarios_by_incremental_profit, run_full_sensitivity
from .validation import run_full_validation
from . import report as report_mod

REPO_ROOT = Path(__file__).resolve().parents[2]


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def cmd_run(args: argparse.Namespace) -> None:
    input_dir = Path(args.input_dir)
    src = DummyFileInputSource(
        input_dir,
        assumptions_file=Path(args.assumptions).name if args.assumptions else "assumptions.json",
    )
    if args.assumptions:
        src.assumptions_path = Path(args.assumptions)

    assumptions, as_of_date = src.load_assumptions()
    regions = src.load_regions()
    reward_levels = src.load_reward_levels()
    scenarios = src.load_scenarios()

    assumptions_version = f"{Path(src.assumptions_path).name}@{as_of_date}"
    results = compute_all_scenarios(scenarios, regions, reward_levels, assumptions, assumptions_version)
    ranked_excl = rank_scenarios_by_incremental_profit(results, include_initial=False)
    ranked_incl = rank_scenarios_by_incremental_profit(results, include_initial=True)

    sensitivity = {}
    scenario_by_id = {s.scenario_id: s for s in scenarios}
    top_ids = [r.scenario_id for r in ranked_excl[: args.sensitivity_top_n]]
    for sid in top_ids:
        sc = scenario_by_id[sid]
        sensitivity[sid] = run_full_sensitivity(
            sc, regions[sc.region_id], reward_levels[sc.reward_level_id], assumptions, assumptions_version
        )

    validation = run_full_validation(assumptions, regions, reward_levels, scenarios, results)

    out_dir = Path(args.out) if args.out else (REPO_ROOT / "output" / f"run_{_now_ts()}")
    out_dir.mkdir(parents=True, exist_ok=True)

    input_hashes = {}
    for p in (src.assumptions_path, src.reward_levels_path, src.regions_path, src.scenarios_path):
        p = p.resolve()
        if p.exists():
            try:
                label = str(p.relative_to(REPO_ROOT))
            except ValueError:
                label = str(p)
            input_hashes[label] = sha256_of_file(p)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "calc_version": config.CALC_VERSION,
        "random_seed_for_dummy_data": config.RANDOM_SEED,
        "as_of_date": as_of_date,
        "assumptions_version": assumptions_version,
        "input_file_hashes": input_hashes,
        "is_dummy_data": True,
        "note": "본 실행은 가상(더미) 입력 데이터를 사용한 결과입니다. 실제 사업 수치가 아닙니다.",
    }
    with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    with open(out_dir / "assumptions_used.json", "w", encoding="utf-8") as f:
        json.dump({"as_of_date": as_of_date, "assumptions": [asdict(a) for a in assumptions.values()]},
                   f, ensure_ascii=False, indent=2)

    with open(out_dir / "pnl_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "results": [asdict(r) for r in results],
            "ranking_excl_initial": [r.scenario_id for r in ranked_excl],
            "ranking_incl_initial": [r.scenario_id for r in ranked_incl],
        }, f, ensure_ascii=False, indent=2)

    with open(out_dir / "sensitivity_results.json", "w", encoding="utf-8") as f:
        json.dump(sensitivity, f, ensure_ascii=False, indent=2)

    with open(out_dir / "validation_report.json", "w", encoding="utf-8") as f:
        json.dump(validation.to_dict(), f, ensure_ascii=False, indent=2)

    report_path = out_dir / "report_ko.md"
    report_mod.render_report(out_dir, report_path)

    print(f"실행 완료 -> {out_dir}")
    print(f"  확대 권고 가능 여부: {validation.expansion_recommendation_allowed}")
    if validation.has_critical:
        print("  [경고] 치명적 검증 실패 항목이 있습니다. report_ko.md 를 확인하세요.")


def cmd_ingest_pilot(args: argparse.Namespace) -> None:
    ledger_path = Path(args.ledger)
    ledger = load_ledger(ledger_path)

    ingest_log = []
    for f in args.conversion_file or []:
        ingest_log.append(ingest_conversion_file(f, ledger))
    for f in args.repeat_file or []:
        ingest_log.append(ingest_repeat_file(f, ledger))
    save_ledger(ledger, ledger_path)

    conv_rates = compute_conversion_rates(ledger, args.as_of, config.MIN_PILOT_SAMPLE_SIZE)
    repeat_rates = compute_repeat_purchase_rates(ledger, args.as_of, config.MIN_PILOT_SAMPLE_SIZE)
    all_rates = {**conv_rates, **repeat_rates}

    src = DummyFileInputSource(Path(args.assumptions_in).parent, assumptions_file=Path(args.assumptions_in).name)
    base_assumptions, _ = src.load_assumptions()

    updated_assumptions, applied, warnings = apply_rate_updates(base_assumptions, all_rates, args.as_of)

    out_path = Path(args.assumptions_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "_comment": "파일럿 실적 반영 결과. 관찰기간이 완료된 표본만 갱신되었습니다. 가상 예제 데이터 기반입니다.",
            "as_of_date": args.as_of,
            "assumptions": [asdict(a) for a in updated_assumptions.values()],
        }, f, ensure_ascii=False, indent=2)

    update_report = {
        "as_of_date": args.as_of,
        "ledger_path": str(ledger_path),
        "ingest_log": [asdict(r) for r in ingest_log],
        "rate_estimates": {k: asdict(v) for k, v in all_rates.items()},
        "applied_updates": applied,
        "warnings": warnings,
        "assumptions_out": str(out_path),
    }
    if args.update_report_out:
        Path(args.update_report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.update_report_out, "w", encoding="utf-8") as f:
            json.dump(update_report, f, ensure_ascii=False, indent=2)

    print(json.dumps(update_report, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="yakoo_sim", description="야쿠헌터즈 사업성 시뮬레이션")
    sub = p.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="시나리오 손익 + 민감도 + 검증 실행")
    run_p.add_argument("--input-dir", default=str(REPO_ROOT / "data" / "input"))
    run_p.add_argument("--assumptions", default=None, help="기본값 대신 사용할 assumptions.json 경로")
    run_p.add_argument("--out", default=None)
    run_p.add_argument("--sensitivity-top-n", type=int, default=3)
    run_p.set_defaults(func=cmd_run)

    ing_p = sub.add_parser("ingest-pilot", help="파일럿 실적 반영 (중복 방지) 및 가정 갱신")
    ing_p.add_argument("--ledger", default=str(REPO_ROOT / "data" / "ledger" / "pilot_ledger.json"))
    ing_p.add_argument("--conversion-file", nargs="*", default=[])
    ing_p.add_argument("--repeat-file", nargs="*", default=[])
    ing_p.add_argument("--as-of", required=True)
    ing_p.add_argument("--assumptions-in", default=str(REPO_ROOT / "data" / "input" / "assumptions.json"))
    ing_p.add_argument("--assumptions-out", required=True)
    ing_p.add_argument("--update-report-out", default=None)
    ing_p.set_defaults(func=cmd_ingest_pilot)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
