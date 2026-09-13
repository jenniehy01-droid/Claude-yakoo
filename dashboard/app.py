"""야쿠헌터즈 사업성 시뮬레이션 — 로컬 대시보드 (1차 버전).

중요: 이 대시보드는 손익 계산식을 직접 구현하지 않는다. 모든 계산은
`src/yakoo_sim` 의 검증된(pytest로 테스트된) 계산기 함수를 그대로 호출한
결과만 사용한다:
  - yakoo_sim.calculator.compute_scenario_pnl / compute_all_scenarios
  - yakoo_sim.scenarios.rank_scenarios_by_incremental_profit
  - yakoo_sim.validation.validate_assumptions / ScenarioPnL.reconcile

로컬 전용, 오프라인 실행:
  - Flask 개발 서버로 로컬(127.0.0.1)에서만 구동한다. 외부 API/DB 연결 없음.
  - 그래프는 matplotlib으로 서버에서 PNG 렌더링 후 base64로 임베드한다
    (브라우저가 외부 CDN에 접속할 필요 없음).

실행:
  PYTHONPATH=src FLASK_APP=dashboard/app.py flask run
  또는
  python3 dashboard/app.py
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from flask import Flask, render_template, request  # noqa: E402


def _configure_korean_font() -> None:
    """그래프에 한글 라벨이 깨지지 않도록, 설치된 폰트 중 한글 지원 폰트를 찾아 적용한다.

    로컬 실행 환경(Windows/Mac/Linux)마다 설치된 폰트가 다르므로, 흔히 쓰이는
    한글 폰트 이름을 후보로 두고 시스템에 실제로 설치된 것만 사용한다. 하나도
    없으면 기본 폰트로 동작하되(한글이 네모(□)로 보일 수 있음) 대시보드 자체는
    계속 정상 작동한다 — README에 해결 방법(예: `fonts-nanum` 설치)을 안내한다.
    """
    candidates = [
        "NanumGothic", "Malgun Gothic", "AppleGothic", "Apple SD Gothic Neo",
        "Noto Sans CJK KR", "Noto Sans KR", "UnDotum", "Batang",
    ]
    # matplotlib의 폰트 캐시가 최근에 설치된 폰트를 놓칠 수 있으므로, 시스템을
    # 다시 스캔해 후보 폰트를 찾고, 발견하면 전역 FontManager에 명시적으로
    # 등록(addfont)한 뒤 사용한다.
    fresh = fm.FontManager()
    by_name = {f.name: f.fname for f in fresh.ttflist}
    for name in candidates:
        if name in by_name:
            fm.fontManager.addfont(by_name[name])
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


_configure_korean_font()

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from yakoo_sim import config as yakoo_config  # noqa: E402
from yakoo_sim.calculator import compute_all_scenarios, compute_scenario_pnl  # noqa: E402
from yakoo_sim.io_loader import DummyFileInputSource  # noqa: E402
from yakoo_sim.models import Assumption, Scenario  # noqa: E402
from yakoo_sim.scenarios import rank_scenarios_by_incremental_profit  # noqa: E402
from yakoo_sim.validation import validate_assumptions  # noqa: E402

app = Flask(__name__)


@app.template_filter("won")
def won_filter(v) -> str:
    try:
        return f"{float(v):,.0f}원"
    except (TypeError, ValueError):
        return str(v)


INPUT_DIR = REPO_ROOT / "data" / "input"

# 대시보드에서 사용자가 직접 조정할 수 있는 가정값 목록.
# (conversion_observation_window_days / repeat_purchase_observation_window_days 는
#  손익 계산식(calculator.py)에서 사용되지 않으므로 — 파일럿 갱신 로직 전용 —
#  대시보드 조정 대상에서 제외한다. 계산식에 실제로 쓰이는 값만 노출한다.)
OVERRIDABLE_KEYS = [
    ("conversion_rate_domestic_treatment", "전환율 · 국내고객 · 야쿠헌터즈(실험군)", "ratio"),
    ("conversion_rate_tourist_treatment", "전환율 · 관광객 · 야쿠헌터즈(실험군)", "ratio"),
    ("conversion_rate_domestic_control", "전환율 · 국내고객 · 일반판촉(비교군)", "ratio"),
    ("conversion_rate_tourist_control", "전환율 · 관광객 · 일반판촉(비교군)", "ratio"),
    ("avg_order_value_domestic", "평균 객단가 · 국내고객", "KRW"),
    ("avg_order_value_tourist", "평균 객단가 · 관광객", "KRW"),
    ("repeat_purchase_rate_domestic", "재구매율 · 국내고객", "ratio"),
    ("avg_repeat_orders_per_repeat_customer_domestic", "재구매 고객당 평균 재구매 횟수", "count"),
    ("regular_promo_cost_per_conversion", "일반판촉 전환 1건당 비용", "KRW"),
    ("delivery_cost_per_order_domestic", "배송비 · 국내 1건당", "KRW"),
    ("initial_production_cost_program", "초기 제작비(1회성, 프로그램 전체)", "KRW"),
]


def list_assumption_files() -> list[tuple[str, str]]:
    """data/input/assumptions*.json 목록을 (상대경로, 표시라벨)로 반환."""
    files = sorted(INPUT_DIR.glob("assumptions*.json"))
    out = []
    for f in files:
        src = DummyFileInputSource(INPUT_DIR, assumptions_file=f.name)
        try:
            _, as_of = src.load_assumptions()
        except Exception:
            as_of = "?"
        label = f"{f.name} (기준일 {as_of})"
        out.append((str(f.relative_to(REPO_ROOT)), label))
    return out


def load_source(assumptions_rel_path: str) -> DummyFileInputSource:
    p = REPO_ROOT / assumptions_rel_path
    return DummyFileInputSource(p.parent, assumptions_file=p.name)


def apply_overrides(base_assumptions: dict[str, Assumption], form) -> tuple[dict[str, Assumption], list[str]]:
    """폼에서 제출된 값으로 가정을 덮어쓴다. 원래 값과 다르면 '대시보드 수정'으로 명확히 표시한다."""
    updated = dict(base_assumptions)
    overridden_keys = []
    for key, _, _ in OVERRIDABLE_KEYS:
        raw = form.get(f"assumption__{key}", "").strip()
        if raw == "" or key not in base_assumptions:
            continue
        try:
            new_value = float(raw)
        except ValueError:
            continue
        original = base_assumptions[key]
        if abs(new_value - original.value) > 1e-12:
            updated[key] = Assumption(
                key=key, value=new_value, unit=original.unit,
                value_type="가정(대시보드 수정)",
                source="대시보드 화면에서 사용자가 직접 입력한 값 — 검증되지 않은 임시 가정",
                period="현재 세션",
            )
            overridden_keys.append(key)
    return updated, overridden_keys


def fig_to_base64() -> str:
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def render_scenario_comparison_chart(base_results, compare_results=None) -> str:
    labels = [r.label for r in base_results]
    base_values = [r.incremental_profit_excl_initial for r in base_results]

    x = range(len(labels))
    width = 0.35 if compare_results else 0.6

    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.1), 4.5))
    ax.bar([i - (width / 2 if compare_results else 0) for i in x], base_values, width=width,
           label="기준(Base) 가정", color="#3b6fd6")
    if compare_results:
        compare_values = [r.incremental_profit_excl_initial for r in compare_results]
        ax.bar([i + width / 2 for i in x], compare_values, width=width,
               label="비교(Compare) 가정", color="#e0763a")
    ax.axhline(0, color="#888", linewidth=0.8)
    ax.set_ylabel("증분이익 (초기제작비 제외, 원)")
    ax.set_title("시나리오별 증분이익 비교 (일반판촉 대비 야쿠헌터즈)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.legend()
    fig.tight_layout()
    return fig_to_base64()


@app.route("/", methods=["GET", "POST"])
def index():
    assumption_files = list_assumption_files()
    default_base = assumption_files[0][0] if assumption_files else None

    src0 = load_source(default_base)
    regions0 = src0.load_regions()
    reward_levels0 = src0.load_reward_levels()
    scenarios0 = src0.load_scenarios()

    form_state = {
        "base_assumptions_file": request.form.get("base_assumptions_file", default_base),
        "compare_assumptions_file": request.form.get("compare_assumptions_file", ""),
        "scenario_id": request.form.get("scenario_id", scenarios0[0].scenario_id if scenarios0 else ""),
        "region_id": request.form.get("region_id", scenarios0[0].region_id if scenarios0 else ""),
        "fm_count": request.form.get("fm_count", str(scenarios0[0].fm_count) if scenarios0 else "5"),
        "reward_level_id": request.form.get("reward_level_id",
                                             scenarios0[0].reward_level_id if scenarios0 else ""),
    }

    # 시나리오 드롭다운을 고르면(브라우저 JS로) 지역/FM수/보상수준 입력칸을 자동
    # 채워 넣을 수 있도록 시나리오 목록을 JSON으로 함께 내려준다. 서버 재요청 없이
    # 다른 입력값(가정 오버라이드 등)을 그대로 유지하기 위함이다.
    scenario_presets = {
        s.scenario_id: {
            "region_id": s.region_id, "fm_count": s.fm_count,
            "reward_level_id": s.reward_level_id, "label": s.label,
        }
        for s in scenarios0
    }

    base_src = load_source(form_state["base_assumptions_file"])
    base_assumptions, base_as_of = base_src.load_assumptions()
    regions = base_src.load_regions()
    reward_levels = base_src.load_reward_levels()
    scenarios = base_src.load_scenarios()

    assumption_rows = []
    for key, kr_label, unit in OVERRIDABLE_KEYS:
        a = base_assumptions.get(key)
        assumption_rows.append({
            "key": key, "label": kr_label, "unit": unit,
            "value": a.value if a else "",
            "value_type": a.value_type if a else "-",
            "source": a.source if a else "-",
            "period": a.period if a else "-",
            "form_value": request.form.get(f"assumption__{key}", a.value if a else ""),
        })

    result = None
    if request.method == "POST":
        try:
            fm_count = int(float(form_state["fm_count"]))
        except ValueError:
            fm_count = 1
        region = regions.get(form_state["region_id"])
        reward_level = reward_levels.get(form_state["reward_level_id"])

        if region is None or reward_level is None or fm_count <= 0:
            result = {"error": "지역/보상수준/FM 수를 올바르게 선택·입력해 주세요."}
        else:
            base_with_overrides, overridden_keys = apply_overrides(base_assumptions, request.form)
            all_validation_issues = validate_assumptions(base_with_overrides)

            # 대시보드 오버라이드는 value_type을 "가정(대시보드 수정)"으로 표시하므로
            # validate_assumptions()가 "실제/추정/가정 중 하나가 아님"이라고 지적하는
            # 것은 정상(의도된) 동작이다. 이는 실제 데이터 품질 문제가 아니라 "이 값은
            # 검증되지 않은 탐색적 입력"이라는 신호이므로, 다른 구조적 검증 실패
            # (범위 초과, 참조 무결성 등)와는 분리해서 보여준다.
            structural_issues = [
                issue for issue in all_validation_issues
                if not (issue.rule == "assumption_metadata_missing"
                        and any(k in issue.message for k in overridden_keys))
            ]
            using_overrides = bool(overridden_keys)

            focus_scenario = Scenario(
                scenario_id="dashboard_custom", region_id=region.region_id,
                fm_count=fm_count, reward_level_id=reward_level.reward_level_id,
                label=f"{region.region_name} / FM {fm_count}명 / {reward_level.label}",
            )
            base_version = f"{form_state['base_assumptions_file']}@{base_as_of}"
            focus_base = compute_scenario_pnl(focus_scenario, region, reward_level,
                                               base_with_overrides, base_version)
            reconcile_errors = focus_base.reconcile(yakoo_config.RECONCILIATION_TOLERANCE)

            base_all_results = compute_all_scenarios(scenarios, regions, reward_levels,
                                                       base_with_overrides, base_version)
            ranked = rank_scenarios_by_incremental_profit(base_all_results, include_initial=False)

            focus_compare = None
            compare_all_results = None
            compare_as_of = None
            if form_state["compare_assumptions_file"]:
                compare_src = load_source(form_state["compare_assumptions_file"])
                compare_assumptions, compare_as_of = compare_src.load_assumptions()
                compare_version = f"{form_state['compare_assumptions_file']}@{compare_as_of}"
                focus_compare = compute_scenario_pnl(focus_scenario, region, reward_level,
                                                      compare_assumptions, compare_version)
                compare_all_results = compute_all_scenarios(scenarios, regions, reward_levels,
                                                              compare_assumptions, compare_version)

            chart_b64 = render_scenario_comparison_chart(base_all_results, compare_all_results)

            result = {
                "error": None,
                "focus_scenario": focus_scenario,
                "focus_base": focus_base,
                "focus_compare": focus_compare,
                "overridden_keys": overridden_keys,
                "using_overrides": using_overrides,
                "validation_issues": structural_issues,
                "reconcile_errors": reconcile_errors,
                "expansion_allowed": (not using_overrides and len(structural_issues) == 0
                                      and len(reconcile_errors) == 0),
                "ranked_labels": [r.label for r in ranked[:3]],
                "chart_b64": chart_b64,
                "base_as_of": base_as_of,
                "compare_as_of": compare_as_of,
            }

    return render_template(
        "index.html",
        assumption_files=assumption_files,
        form_state=form_state,
        regions=regions0,
        reward_levels=reward_levels0,
        scenarios=scenarios0,
        scenario_presets_json=json.dumps(scenario_presets, ensure_ascii=False),
        assumption_rows=assumption_rows,
        result=result,
        calc_version=yakoo_config.CALC_VERSION,
        random_seed=yakoo_config.RANDOM_SEED,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
