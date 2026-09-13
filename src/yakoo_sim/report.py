"""검증된 Python 실행 결과(JSON)만 읽어 한국어 사업성 보고서를 작성한다.

이 모듈은 새로운 손익 수치를 계산하지 않는다 — run_dir 안의
pnl_results.json / sensitivity_results.json / validation_report.json /
manifest.json / assumptions_used.json 에 이미 저장된 값을 서식화할 뿐이다.
"""
from __future__ import annotations

import json
from pathlib import Path


def _load(run_dir: Path, name: str) -> dict:
    with open(run_dir / name, encoding="utf-8") as f:
        return json.load(f)


def _won(v: float) -> str:
    return f"{v:,.0f}원"


def render_report(run_dir: str | Path, out_path: str | Path) -> None:
    run_dir = Path(run_dir)
    manifest = _load(run_dir, "manifest.json")
    assumptions_used = _load(run_dir, "assumptions_used.json")
    pnl = _load(run_dir, "pnl_results.json")
    sensitivity = _load(run_dir, "sensitivity_results.json")
    validation = _load(run_dir, "validation_report.json")

    results_by_id = {r["scenario_id"]: r for r in pnl["results"]}
    ranked_excl = pnl["ranking_excl_initial"]
    ranked_incl = pnl["ranking_incl_initial"]

    lines: list[str] = []
    lines.append("# 야쿠헌터즈 사업성 시뮬레이션 결과 보고서")
    lines.append("")
    lines.append("> **[가상 데이터 안내]** 이 보고서의 모든 수치는 `data/input/`의 "
                  "**가상(더미) 예제 데이터**를 입력으로 실행한 Python 계산 결과입니다. "
                  "실제 사업/고객 데이터가 아니며, 외부 API나 사내 DB에 연결되어 있지 않습니다.")
    lines.append("")
    lines.append("## 0. 실행 정보 (재현성)")
    lines.append("")
    lines.append(f"- 계산 프로그램 버전: `{manifest['calc_version']}`")
    lines.append(f"- 가정 버전(assumptions_version): `{manifest['assumptions_version']}`")
    lines.append(f"- 가정 기준일(as_of_date): `{manifest['as_of_date']}`")
    lines.append(f"- 더미 예제 데이터 생성 난수 시드: `{manifest['random_seed_for_dummy_data']}`")
    lines.append(f"- 실행 시각(UTC): `{manifest['generated_at']}`")
    lines.append("- 입력 파일 해시(SHA-256):")
    for path, digest in manifest["input_file_hashes"].items():
        lines.append(f"  - `{path}`: `{digest[:16]}...`")
    lines.append("")

    lines.append("## 1. 데이터 검증 결과")
    lines.append("")
    allowed = validation["expansion_recommendation_allowed"]
    if allowed:
        lines.append("✅ 치명적 검증 실패 없음 — 아래 결과를 근거로 확대 여부를 논의할 수 있습니다.")
    else:
        lines.append("🚫 **치명적 검증 실패가 발견되어 확대 권고를 보류합니다.** "
                      "아래 항목을 해결한 뒤 재실행이 필요합니다.")
    critical = [i for i in validation["issues"] if i["severity"] == "critical"]
    warnings = [i for i in validation["issues"] if i["severity"] == "warning"]
    if critical:
        lines.append("")
        lines.append("**치명적 오류:**")
        for i in critical:
            lines.append(f"- [{i['rule']}] {i['message']}")
    if warnings:
        lines.append("")
        lines.append("**경고(참고용):**")
        for i in warnings:
            lines.append(f"- [{i['rule']}] {i['message']}")
    lines.append("")

    lines.append("## 2. 시나리오별 손익 비교 (일반 판촉 vs 야쿠헌터즈)")
    lines.append("")
    lines.append("| 시나리오 | 지역 | 보상수준 | 야쿠헌터즈 이익(초기비용 제외) | 일반판촉 이익 | "
                  "**증분이익(초기비용 제외)** | 야쿠헌터즈 이익(초기비용 포함) | **증분이익(초기비용 포함)** |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|")
    for r in pnl["results"]:
        lines.append(
            f"| {r['label']} | {r['region_id']} | {r['reward_level_id']} | "
            f"{_won(r['treatment']['profit_excl_initial'])} | {_won(r['control']['profit_excl_initial'])} | "
            f"**{_won(r['incremental_profit_excl_initial'])}** | "
            f"{_won(r['treatment']['profit_incl_initial'])} | "
            f"**{_won(r['incremental_profit_incl_initial'])}** |"
        )
    lines.append("")

    lines.append("### 2.1 증분이익(초기 제작비 제외) 상위 시나리오")
    lines.append("")
    for sid in ranked_excl[:3]:
        r = results_by_id[sid]
        lines.append(f"1. **{r['label']}** — 증분이익 {_won(r['incremental_profit_excl_initial'])}")
    lines.append("")
    lines.append("### 2.2 증분이익(초기 제작비 포함) 상위 시나리오")
    lines.append("")
    for sid in ranked_incl[:3]:
        r = results_by_id[sid]
        lines.append(f"1. **{r['label']}** — 증분이익 {_won(r['incremental_profit_incl_initial'])}")
    lines.append("")
    lines.append("> 초기 제작비(홍보물/키트 등 1회성 비용)는 실험군(야쿠헌터즈)에만 반영됩니다. "
                  "규모가 커질수록 초기 제작비의 시나리오당 영향은 상대적으로 작아집니다.")
    lines.append("")

    lines.append("## 3. 민감도 분석 (상위 시나리오 대상)")
    lines.append("")
    lines.append("가정값을 -20%~+20% 범위에서 결정론적으로 조정했을 때 증분이익(초기비용 제외)이 "
                  "어떻게 변하는지 보여줍니다. 확률분포나 난수로 만들어낸 값이 아니라, "
                  "지정된 변화율을 그대로 대입한 재계산 결과입니다.")
    lines.append("")
    for sid, key_results in sensitivity.items():
        label = results_by_id[sid]["label"]
        lines.append(f"### {label} (`{sid}`)")
        lines.append("")
        for vary_key, rows in key_results.items():
            lines.append(f"**{vary_key}**")
            lines.append("")
            lines.append("| 변화율 | 값 | 증분이익(초기비용 제외) |")
            lines.append("|---:|---:|---:|")
            for row in rows:
                lines.append(f"| {row['delta']:+.0%} | {row['value']:.4f} | "
                              f"{_won(row['incremental_profit_excl_initial'])} |")
            lines.append("")

    lines.append("## 4. 사용된 가정값 (실제 / 추정 / 가정 구분)")
    lines.append("")
    lines.append("| 항목 | 값 | 구분 | 출처 | 기준기간 |")
    lines.append("|---|---:|---|---|---|")
    for a in assumptions_used["assumptions"]:
        lines.append(f"| {a['key']} | {a['value']} | {a['value_type']} | {a['source']} | {a['period']} |")
    lines.append("")

    lines.append("## 5. 결론 및 다음 단계")
    lines.append("")
    if allowed:
        best = results_by_id[ranked_excl[0]]
        lines.append(
            f"현재 가상 예제 데이터 기준으로는 **{best['label']}** 시나리오의 증분이익(초기비용 제외)이 "
            f"{_won(best['incremental_profit_excl_initial'])}로 가장 높습니다. "
            "다만 이는 가상 데이터 기반 결과이므로, 실제 확대 투자 결정 전에 파일럿 실적 반영 후 "
            "재계산된 결과로 다시 확인해야 합니다."
        )
    else:
        lines.append("치명적 검증 실패로 인해 이번 실행 결과만으로는 확대(규모 확장) 권고를 제시하지 않습니다. "
                      "1절의 오류를 해결한 뒤 재실행하십시오.")
    lines.append("")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
