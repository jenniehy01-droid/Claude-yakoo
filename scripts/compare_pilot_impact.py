#!/usr/bin/env python3
"""세 번의 실행(베이스라인 / 파일럿 반영 2026-09-01 / 파일럿 반영 2026-12-01) 결과를
비교하는 표를 만든다. 이미 각 run_dir에 저장된 Python 실행 결과(JSON)만 읽어서
서식화할 뿐, 새로운 손익 계산을 하지 않는다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_results(run_dir: Path) -> dict:
    with open(run_dir / "pnl_results.json", encoding="utf-8") as f:
        data = json.load(f)
    return {r["scenario_id"]: r for r in data["results"]}


def load_manifest(run_dir: Path) -> dict:
    with open(run_dir / "manifest.json", encoding="utf-8") as f:
        return json.load(f)


def won(v: float) -> str:
    return f"{v:,.0f}원"


def main():
    runs = [
        ("베이스라인 (파일럿 반영 전)", ROOT / "output" / "run_baseline"),
        ("파일럿 1차 반영 (as_of 2026-09-01)", ROOT / "output" / "run_after_pilot_2026-09-01"),
        ("파일럿 2차 반영 (as_of 2026-12-01, 신규 파일 없이 재계산)", ROOT / "output" / "run_after_pilot_2026-12-01"),
    ]

    lines = ["# 파일럿 데이터 반영 전/후 손익 변화 재현 결과", ""]
    lines.append("> 아래 수치는 모두 각 실행 시점의 `output/run_*/pnl_results.json` (Python 실행 결과)에서 그대로 가져온 값입니다.")
    lines.append("")

    for label, run_dir in runs:
        manifest = load_manifest(run_dir)
        lines.append(f"## {label}")
        lines.append(f"- assumptions_version: `{manifest['assumptions_version']}`")
        lines.append(f"- as_of_date: `{manifest['as_of_date']}`")
        lines.append("")

    all_results = [load_results(rd) for _, rd in runs]
    scenario_ids = list(all_results[0].keys())

    lines.append("## 시나리오별 증분이익(초기비용 제외) 비교")
    lines.append("")
    header = "| 시나리오 | " + " | ".join(label for label, _ in runs) + " |"
    sep = "|---|" + "---:|" * len(runs)
    lines.append(header)
    lines.append(sep)
    for sid in scenario_ids:
        row = [all_results[i][sid]["incremental_profit_excl_initial"] for i in range(len(runs))]
        label = all_results[0][sid]["label"]
        lines.append(f"| {label} | " + " | ".join(won(v) for v in row) + " |")
    lines.append("")

    lines.append("## 가정값 변화 요약 (파일럿 반영으로 갱신된 항목)")
    lines.append("")
    for label, run_dir in runs[1:]:
        update_report_path = None
        if "2026-09-01" in str(run_dir):
            update_report_path = ROOT / "output" / "pilot_update_2026-09-01.json"
        elif "2026-12-01" in str(run_dir):
            update_report_path = ROOT / "output" / "pilot_update_2026-12-01.json"
        if update_report_path and update_report_path.exists():
            with open(update_report_path, encoding="utf-8") as f:
                upd = json.load(f)
            lines.append(f"### {label}")
            lines.append("")
            lines.append("| 가정 항목 | 이전 값 | 갱신 값 | 표본크기 |")
            lines.append("|---|---:|---:|---:|")
            for a in upd["applied_updates"]:
                lines.append(f"| {a['key']} | {a['old_value']} | {a['new_value']:.4f} | {a['sample_size']} |")
            if upd["warnings"]:
                lines.append("")
                lines.append("경고(표본 부족 등으로 갱신 보류):")
                for w in upd["warnings"]:
                    lines.append(f"- {w}")
            lines.append("")

    out_path = ROOT / "output" / "pilot_impact_comparison.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
