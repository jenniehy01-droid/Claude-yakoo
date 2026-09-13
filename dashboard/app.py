"""야쿠헌터즈 사업성 시뮬레이션 — 로컬 대시보드.

첫 화면은 "파일럿 투자 의사결정"에 맞춰 구성되어 있다:
  ① 이번에 결정할 사항 → ② 실행안 비교 → ③ 판단을 바꾸는 조건
  → ④ 승인 전에 필요한 근거 → ⑤ 파일럿 후 확대 판단
세부 입력과 계산식은 "가정·계산 근거" 탭에, 파일럿 실적 업로드는 별도 탭에 둔다.

중요: 이 대시보드는 손익 계산식을 직접 구현하지 않는다. 모든 계산은
`src/yakoo_sim` 의 검증된(pytest로 테스트된) 함수를 그대로 호출한 결과다:
  - calculator.compute_scenario_pnl / incremental_revenue / incremental_cost /
    incremental_new_customers / compute_incremental_cac
  - scenarios.compute_scenario_bands / run_full_sensitivity / rank_drivers_by_swing
  - breakeven.solve_breakeven_assumption / solve_breakeven_reward_cost
  - decision_inputs.* (근거 체크리스트·확대 기준)
  - pilot_update.* (파일럿 업로드, 고객 단위 중복 방지 ledger 포함)
  - validation.validate_assumptions

로컬 전용, 오프라인 실행:
  - Flask 개발 서버로 127.0.0.1 에서만 구동한다. 외부 API/DB 연결 없음.
  - 그래프는 matplotlib으로 서버에서 PNG 렌더링 후 base64로 임베드한다.

실행:
  PYTHONPATH=src python3 dashboard/app.py
"""
from __future__ import annotations

import base64
import io
import json
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from flask import Flask, render_template, request  # noqa: E402
from werkzeug.utils import secure_filename  # noqa: E402


def _configure_korean_font() -> None:
    """그래프에 한글 라벨이 깨지지 않도록, 설치된 폰트 중 한글 지원 폰트를 찾아 적용한다.
    하나도 없으면 기본 폰트로 동작하되(한글이 네모(□)로 보일 수 있음) 대시보드 자체는
    계속 정상 작동한다 — README에 해결 방법(예: `fonts-nanum` 설치)을 안내한다."""
    candidates = [
        "NanumGothic", "Malgun Gothic", "AppleGothic", "Apple SD Gothic Neo",
        "Noto Sans CJK KR", "Noto Sans KR", "UnDotum", "Batang",
    ]
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
from yakoo_sim.breakeven import solve_breakeven_assumption, solve_breakeven_reward_cost  # noqa: E402
from yakoo_sim.calculator import (  # noqa: E402
    compute_incremental_cac,
    compute_scenario_pnl,
    incremental_cost,
    incremental_new_customers,
    incremental_revenue,
)
from yakoo_sim.decision_inputs import (  # noqa: E402
    evaluate_expansion_criterion,
    get_readiness_value,
    load_decision_readiness,
    load_expansion_criteria,
    pilot_conversion_gap_pp,
    readiness_summary,
)
from yakoo_sim.io_loader import DummyFileInputSource  # noqa: E402
from yakoo_sim.models import Assumption, RewardLevel, Scenario  # noqa: E402
from yakoo_sim.pilot_update import (  # noqa: E402
    apply_rate_updates,
    compute_conversion_rates,
    compute_repeat_purchase_rates,
    ingest_conversion_file,
    ingest_repeat_file,
    load_ledger,
    save_ledger,
)
from yakoo_sim.scenarios import (  # noqa: E402
    BAND_DEFINITIONS,
    compute_scenario_bands,
    rank_drivers_by_swing,
    run_full_sensitivity,
)
from yakoo_sim.validation import validate_assumptions  # noqa: E402

app = Flask(__name__)

INPUT_DIR = REPO_ROOT / "data" / "input"
LEDGER_PATH = REPO_ROOT / "data" / "ledger" / "pilot_ledger.json"
UPLOAD_DIR = REPO_ROOT / "data" / "input" / "pilot" / "dashboard_uploads"
READINESS_PATH = INPUT_DIR / "decision_readiness.csv"
EXPANSION_PATH = INPUT_DIR / "expansion_criteria.csv"

BAND_NAMES = [name for name, _ in BAND_DEFINITIONS]


# ---------------------------------------------------------------------------
# 서식 — 금액은 원/만원 단위를 명확히, 이익·손실은 부호와 문구로 함께 구분한다.
# ---------------------------------------------------------------------------

@app.template_filter("won")
def won_filter(v) -> str:
    try:
        return f"{float(v):,.0f}원"
    except (TypeError, ValueError):
        return str(v)


@app.template_filter("manwon")
def manwon_filter(v) -> str:
    try:
        return f"{float(v) / 10000:,.0f}만원"
    except (TypeError, ValueError):
        return str(v)


@app.template_filter("signed_manwon")
def signed_manwon_filter(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{'+' if v >= 0 else '-'}{abs(v) / 10000:,.0f}만원"


@app.template_filter("cleannum")
def cleannum_filter(v) -> str:
    """천 단위 구분 기호를 넣고 불필요한 소수점은 없앤다 (8000.0 -> 8,000)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.1f}"


@app.template_filter("people")
def people_filter(v) -> str:
    try:
        return f"{float(v):,.0f}명"
    except (TypeError, ValueError):
        return str(v)


def _clean_num(v) -> str:
    """불필요한 소수점을 없앤다 (16.0 -> 16, 8000.0 -> 8000, 16.25 -> 16.25)."""
    v = float(v)
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _display_str(value: float | None, kind: str) -> str | None:
    if value is None:
        return None
    if kind == "ratio":
        return f"{value * 100:.1f}".rstrip("0").rstrip(".") + "%"
    return f"{value:.2f}".rstrip("0").rstrip(".") + "회"


# ---------------------------------------------------------------------------
# 가정값 항목 정의 — key, 표시라벨, 종류(ratio=%/krw=원/count=횟수),
# 배치(top=핵심 / detail=상세설정), 분모 설명(비율만).
# ---------------------------------------------------------------------------
OVERRIDABLE_KEYS = [
    ("conversion_rate_domestic_treatment", "첫 구매율 (야쿠헌터즈)", "ratio", "top",
     "분모: 프레시매니저가 접촉한 국내 배송 가능 잠재고객 수"),
    ("repeat_purchase_rate_domestic", "재구매율 (국내 고객)", "ratio", "top",
     "분모: 첫 구매한 국내 배송 고객 수 (관찰기간 내 재구매 여부)"),
    ("conversion_rate_tourist_treatment", "첫 구매율 · 관광객 (야쿠헌터즈)", "ratio", "detail",
     "분모: 프레시매니저가 접촉한 관광객 수"),
    ("conversion_rate_domestic_control", "첫 구매율 · 국내 (일반판촉, 비교기준)", "ratio", "detail",
     "분모: 일반판촉으로 접촉한 국내 배송 가능 고객 수"),
    ("conversion_rate_tourist_control", "첫 구매율 · 관광객 (일반판촉, 비교기준)", "ratio", "detail",
     "분모: 일반판촉으로 접촉한 관광객 수"),
    ("avg_order_value_domestic", "평균 객단가 · 국내 고객", "krw", "detail", None),
    ("avg_order_value_tourist", "평균 객단가 · 관광객", "krw", "detail", None),
    ("avg_repeat_orders_per_repeat_customer_domestic", "재구매 고객당 평균 재구매 횟수", "count", "detail", None),
    ("regular_promo_cost_per_conversion", "일반판촉 전환 1건당 비용", "krw", "detail", None),
    ("delivery_cost_per_order_domestic", "배송비 · 국내 1건당", "krw", "detail", None),
    ("initial_production_cost_program", "초기 제작비 (1회성, 전체)", "krw", "detail", None),
]
KEY_LABELS = {k: label for k, label, *_ in OVERRIDABLE_KEYS}
KEY_KIND = {k: kind for k, _label, kind, *_ in OVERRIDABLE_KEYS}

DRIVER_CANDIDATE_KEYS = (
    "conversion_rate_domestic_treatment",
    "conversion_rate_tourist_treatment",
    "repeat_purchase_rate_domestic",
    "avg_repeat_orders_per_repeat_customer_domestic",
    "avg_order_value_domestic",
    "regular_promo_cost_per_conversion",
)


def list_assumption_files() -> list[tuple[str, str]]:
    files = sorted(INPUT_DIR.glob("assumptions*.json"))
    out = []
    for f in files:
        src = DummyFileInputSource(INPUT_DIR, assumptions_file=f.name)
        try:
            _, as_of = src.load_assumptions()
        except Exception:
            as_of = "?"
        out.append((str(f.relative_to(REPO_ROOT)), f"{f.name} (기준일 {as_of})"))
    return out


def load_source(assumptions_rel_path: str) -> DummyFileInputSource:
    p = REPO_ROOT / assumptions_rel_path
    return DummyFileInputSource(p.parent, assumptions_file=p.name)


def apply_overrides(base_assumptions: dict[str, Assumption], form) -> tuple[dict[str, Assumption], list[str]]:
    """폼 제출값으로 가정을 덮어쓴다. 비율(ratio)은 화면에 %로 표시되므로 100으로 나눠 저장한다.
    원래 값과 다르면 '대시보드 수정'으로 명확히 구분 표시한다."""
    updated = dict(base_assumptions)
    overridden_keys = []
    for key, _, kind, _tier, _denom in OVERRIDABLE_KEYS:
        raw = form.get(f"assumption__{key}", "").strip()
        if raw == "" or key not in base_assumptions:
            continue
        try:
            raw_value = float(raw)
        except ValueError:
            continue
        new_value = raw_value / 100 if kind == "ratio" else raw_value
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


def resolve_reward_level(cost_value: float, reward_levels: dict[str, RewardLevel]) -> RewardLevel:
    for rl in reward_levels.values():
        if abs(rl.reward_cost_per_conversion - cost_value) < 1e-6:
            return rl
    return RewardLevel(
        reward_level_id="custom", label="사용자 지정 보상비",
        reward_cost_per_conversion=cost_value,
        value_type="가정(대시보드 입력)",
        source="대시보드에서 사용자가 직접 입력한 보상비 — 검증되지 않은 임시 가정",
        period="현재 세션",
    )


def fig_to_base64() -> str:
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def build_scenario(region, fm_count, reward_level, scenario_id="dashboard_custom") -> Scenario:
    return Scenario(
        scenario_id=scenario_id, region_id=region.region_id,
        fm_count=fm_count, reward_level_id=reward_level.reward_level_id,
        label=f"{region.region_name} · FM {fm_count}명 · 보상비 {reward_level.reward_cost_per_conversion:,.0f}원",
    )


# ---------------------------------------------------------------------------
# ② 실행안 비교
# ---------------------------------------------------------------------------

def build_pilot_option(name: str, note: str, fm_count: int, region, reward_level,
                        assumptions, version: str) -> dict:
    """실행안 1개의 비교 지표를 만든다. 필요한 입력이 없으면 '입력 필요'로 표시한다."""
    option = {"key": f"fm{fm_count}", "name": name, "note": note, "fm_count": fm_count,
              "is_baseline": False, "needs_input": False, "missing_reason": None}
    if fm_count <= 0:
        option.update(needs_input=True, missing_reason="참여 인원이 입력되지 않았습니다.")
        return option
    try:
        scenario = build_scenario(region, fm_count, reward_level)
        pnl = compute_scenario_pnl(scenario, region, reward_level, assumptions, version)
        bands = compute_scenario_bands(scenario, region, reward_level, assumptions, version)
    except KeyError as exc:
        option.update(needs_input=True, missing_reason=f"{exc.args[0]}")
        return option
    option.update(
        scenario=scenario,
        pnl=pnl,
        target_customers=pnl.treatment.contacted_total,
        added_cost=incremental_cost(pnl, include_initial=True),
        added_customers=incremental_new_customers(pnl),
        added_profit_incl=pnl.incremental_profit_incl_initial,
        added_profit_excl=pnl.incremental_profit_excl_initial,
        added_revenue=incremental_revenue(pnl),
        incremental_cac=compute_incremental_cac(pnl),
        bands={name: b.incremental_profit_incl_initial for name, b in bands.items()},
    )
    return option


def build_baseline_option() -> dict:
    return {
        "key": "status_quo", "name": "일반 판촉 유지", "note": "파일럿 미실행 · 비교 기준선",
        "fm_count": 0, "is_baseline": True, "needs_input": False, "missing_reason": None,
        "target_customers": 0.0, "added_cost": 0.0, "added_customers": 0.0,
        "added_profit_incl": 0.0, "added_profit_excl": 0.0, "added_revenue": 0.0,
        "incremental_cac": None, "bands": {name: 0.0 for name in BAND_NAMES},
    }


def render_options_chart(options: list[dict]) -> str | None:
    """실행안별 · 수요 가정별 추가 손익(초기 제작비 포함)을 비교한다."""
    plot_options = [o for o in options if not o["is_baseline"] and not o["needs_input"]]
    if not plot_options:
        return None

    band_colors = {"보수": "#b9c6bf", "중간": "#4a8f6b", "낙관": "#0f5132"}
    x = range(len(plot_options))
    width = 0.24

    fig, ax = plt.subplots(figsize=(8.2, 3.8))
    all_values = []
    for i, band in enumerate(BAND_NAMES):
        offset = (i - 1) * width
        values = [o["bands"][band] / 10000 for o in plot_options]
        all_values += values
        bars = ax.bar([xi + offset for xi in x], values, width=width, label=band, color=band_colors[band])
        # 막대 높이 차이가 작아도 값을 읽을 수 있도록 숫자를 직접 표시한다.
        for rect, value in zip(bars, values):
            va = "top" if value < 0 else "bottom"
            ax.annotate(f"{value:,.0f}", (rect.get_x() + rect.get_width() / 2, value),
                        textcoords="offset points", xytext=(0, -13 if value < 0 else 4),
                        ha="center", va=va, fontsize=9.5, color="#1b2420")

    ax.axhline(0, color="#c0392b", linewidth=1.4, linestyle="--")
    ax.set_ylabel("추가 손익 (만원)", fontsize=10)
    ax.set_title("실행안별 추가 손익 (초기 제작비 포함) — 빨간 점선 = 일반 판촉 유지(0)", fontsize=12)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{o['name']} (참여 {o['fm_count']}명)" for o in plot_options], fontsize=11)
    # 숫자 라벨이 잘리지 않도록 위아래 여유를 준다.
    lo, hi = min(all_values + [0]), max(all_values + [0])
    span = (hi - lo) or 1
    ax.set_ylim(lo - span * 0.22, hi + span * 0.18)
    ax.legend(title="수요 가정", frameon=False, fontsize=10, title_fontsize=10,
              loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3)
    fig.tight_layout()
    return fig_to_base64()


# ---------------------------------------------------------------------------
# ③ 판단을 바꾸는 조건 (손익분기)
# ---------------------------------------------------------------------------

BREAKEVEN_LEVERS = [
    ("conversion_rate_domestic_treatment", "첫 구매율", "ratio", 0.0, 1.0),
    ("repeat_purchase_rate_domestic", "재구매율", "ratio", 0.0, 1.0),
]


def _format_lever_value(value: float | None, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "ratio":
        return f"{value * 100:.1f}%"
    return f"{value:,.0f}원"


def _format_gap(gap: float | None, kind: str) -> str:
    if gap is None:
        return "—"
    if kind == "ratio":
        pp = gap * 100
        return f"지금보다 {abs(pp):.1f}%p {'더 높아야' if pp > 0 else '낮아도 됨'}" if pp != 0 else "현재와 동일"
    return f"지금보다 {abs(gap):,.0f}원 {'더 써도 됨' if gap > 0 else '낮춰야'}" if gap != 0 else "현재와 동일"


def _no_crossing_message(kind: str, hi: float, sign: str | None) -> tuple[str, str]:
    """손익분기점이 없을 때의 문구. '항상 손실'과 '항상 이익'은 뜻이 정반대이므로 구분한다.

    반환: (요약 배지 문구, 설명 문구)
    """
    if sign == "always_profit":
        span = f"0%~{hi * 100:.0f}%" if kind == "ratio" else "0원~100만원"
        return "이미 손익분기 이상", f"{span} 어디서도 손실로 바뀌지 않음 (이 값이 걸림돌이 아님)"
    if kind == "ratio":
        return "이 값만으로는 불가", f"{hi * 100:.0f}%까지 올려도 손익분기에 도달하지 않음"
    return "이 값만으로는 불가", "0원까지 낮춰도 손익분기에 도달하지 않음"


def _breakeven_cell(option_name: str, kind: str, hi: float, solve) -> dict:
    """초기 제작비 포함 기준으로 먼저 풀고, 손익분기점이 없으면 제작비 제외 기준을 함께 보여준다."""
    incl = solve(True)
    if incl.unavailable_reason is None:
        return {"option_name": option_name,
                "value": _format_lever_value(incl.breakeven_value, kind),
                "gap": _format_gap(incl.gap, kind),
                "badge": None, "explain": None, "fallback": None,
                "is_good": False}

    badge, explain = _no_crossing_message(kind, hi, incl.endpoints_sign)
    excl = solve(False)
    fallback = None
    if excl.unavailable_reason is None:
        fallback = (f"제작비 제외(운영만) 기준: {_format_lever_value(excl.breakeven_value, kind)} "
                    f"— {_format_gap(excl.gap, kind)}")
    elif excl.endpoints_sign == "always_profit":
        fallback = "제작비 제외(운영만) 기준으로는 이 범위 전체가 이익"
    return {"option_name": option_name, "value": None, "gap": None,
            "badge": badge, "explain": explain, "fallback": fallback,
            "is_good": incl.endpoints_sign == "always_profit"}


def build_breakeven_rows(options: list[dict], region, reward_level, assumptions) -> list[dict]:
    """실행안별로 손익분기(추가손익 = 0) 조건을 계산한다."""
    targets = [o for o in options if not o["is_baseline"] and not o["needs_input"]]
    rows = []
    for key, label, kind, lo, hi in BREAKEVEN_LEVERS:
        row = {"label": label, "kind": kind,
               "current": _format_lever_value(assumptions[key].value if key in assumptions else None, kind),
               "cells": []}
        for opt in targets:
            def solve(include_initial, _opt=opt, _key=key, _label=label, _lo=lo, _hi=hi):
                return solve_breakeven_assumption(_opt["scenario"], region, reward_level, assumptions,
                                                   _key, _label, lo=_lo, hi=_hi,
                                                   include_initial=include_initial)
            row["cells"].append(_breakeven_cell(opt["name"], kind, hi, solve))
        rows.append(row)

    reward_row = {"label": "보상비 (전환 1건당)", "kind": "krw",
                  "current": _format_lever_value(reward_level.reward_cost_per_conversion, "krw"),
                  "cells": []}
    for opt in targets:
        def solve_reward(include_initial, _opt=opt):
            return solve_breakeven_reward_cost(_opt["scenario"], region, reward_level, assumptions,
                                                include_initial=include_initial)
        reward_row["cells"].append(_breakeven_cell(opt["name"], "krw", 0.0, solve_reward))
    rows.append(reward_row)
    return rows


# ---------------------------------------------------------------------------
# ⑤ 파일럿 후 확대 판단
# ---------------------------------------------------------------------------

def build_expansion_rows(as_of: str) -> list[dict]:
    """사전에 정한 확대 기준과, 현재 적재된 파일럿 실적을 비교한다."""
    criteria = load_expansion_criteria(EXPANSION_PATH)
    ledger = load_ledger(LEDGER_PATH)
    has_pilot_data = bool(ledger.get("conversion_records"))

    measured = {}
    if has_pilot_data:
        rates = compute_conversion_rates(ledger, as_of, yakoo_config.MIN_PILOT_SAMPLE_SIZE)
        measured["pilot_conversion_gap"] = pilot_conversion_gap_pp(rates)

    rows = []
    for criterion in criteria:
        value = measured.get(criterion.measurement) if criterion.is_measurable else None
        rows.append(evaluate_expansion_criterion(criterion, value))
    return rows


@app.route("/", methods=["GET", "POST"])
def index():
    assumption_files = list_assumption_files()
    default_assumptions_file = assumption_files[0][0] if assumption_files else None
    form_name = request.form.get("form_name") if request.method == "POST" else None
    active_tab = {"pilot": "pilot", "simulate": request.form.get("return_tab", "decision")}.get(
        form_name, "decision")

    assumptions_file = request.form.get("assumptions_file", default_assumptions_file)
    src = load_source(assumptions_file)
    base_assumptions, as_of_date = src.load_assumptions()
    regions = src.load_regions()
    reward_levels = src.load_reward_levels()

    default_region_id = next(iter(regions)) if regions else None
    default_reward_cost = reward_levels["mid"].reward_cost_per_conversion if "mid" in reward_levels else (
        next(iter(reward_levels.values())).reward_cost_per_conversion if reward_levels else 8000.0)

    form_state = {
        "assumptions_file": assumptions_file,
        "region_id": request.form.get("region_id", default_region_id),
        "small_fm_count": request.form.get("small_fm_count", "3"),
        "large_fm_count": request.form.get("large_fm_count", "10"),
        "reward_cost": request.form.get("reward_cost", _clean_num(default_reward_cost)),
    }

    assumption_rows = []
    for key, label, kind, tier, denom in OVERRIDABLE_KEYS:
        a = base_assumptions.get(key)
        display_value = _clean_num(a.value * 100 if kind == "ratio" else a.value) if a else ""
        assumption_rows.append({
            "key": key, "label": label, "kind": kind, "tier": tier, "denom": denom,
            "value_type": a.value_type if a else "-",
            "source": a.source if a else "-",
            "period": a.period if a else "-",
            "display_value": display_value,
            "form_value": request.form.get(f"assumption__{key}", display_value),
        })
    top_rows = [r for r in assumption_rows if r["tier"] == "top"]
    detail_rows = [r for r in assumption_rows if r["tier"] == "detail"]

    region_info = {rid: {"name": r.region_name, "tourist_share": r.tourist_share,
                          "contacted_per_fm": r.contacted_customers_per_fm,
                          "fixed_cost_per_fm": r.fixed_operation_cost_per_fm}
                   for rid, r in regions.items()}
    reward_presets = {rl.reward_level_id: {"label": rl.label, "cost": rl.reward_cost_per_conversion}
                      for rl in reward_levels.values()}

    # ---------------- 승인 전 근거 (항상 표시) ----------------
    readiness_items = load_decision_readiness(READINESS_PATH)
    readiness = readiness_summary(readiness_items)
    loss_tolerance = get_readiness_value(readiness_items, "loss_tolerance")

    pilot_as_of = request.form.get("as_of_date", date.today().isoformat())
    expansion_rows = build_expansion_rows(pilot_as_of)

    decision_result = None
    basis_result = None
    pilot_result = None

    if form_name == "simulate":
        def _int_or_zero(raw):
            try:
                return max(0, int(float(raw)))
            except ValueError:
                return 0

        small_fm = _int_or_zero(form_state["small_fm_count"])
        large_fm = _int_or_zero(form_state["large_fm_count"])
        try:
            reward_cost = float(form_state["reward_cost"])
        except ValueError:
            reward_cost = default_reward_cost
        region = regions.get(form_state["region_id"])

        if region is None:
            decision_result = {"error": "지역을 선택해 주세요."}
        else:
            assumptions, overridden_keys = apply_overrides(base_assumptions, request.form)
            all_issues = validate_assumptions(assumptions)
            structural_issues = [
                i for i in all_issues
                if not (i.rule == "assumption_metadata_missing" and any(k in i.message for k in overridden_keys))
            ]
            using_overrides = bool(overridden_keys)
            reward_level = resolve_reward_level(reward_cost, reward_levels)
            version = f"{assumptions_file}@{as_of_date}"

            options = [
                build_baseline_option(),
                build_pilot_option("작은 규모 파일럿", "소규모로 근거부터 확보", small_fm,
                                    region, reward_level, assumptions, version),
                build_pilot_option("큰 규모 파일럿", "규모를 키워 빠르게 검증", large_fm,
                                    region, reward_level, assumptions, version),
            ]
            computed = [o for o in options if not o["is_baseline"] and not o["needs_input"]]

            breakeven_rows = build_breakeven_rows(options, region, reward_level, assumptions) if computed else []
            conservative = [{"name": o["name"], "value": o["bands"]["보수"]} for o in computed]

            decision_result = {
                "error": None,
                "region": region,
                "reward_level": reward_level,
                "options": options,
                "chart_b64": render_options_chart(options),
                "breakeven_rows": breakeven_rows,
                "conservative": conservative,
                "loss_tolerance": loss_tolerance,
                "initial_cost": assumptions["initial_production_cost_program"].value
                if "initial_production_cost_program" in assumptions else None,
                "using_overrides": using_overrides,
                "overridden_labels": [KEY_LABELS.get(k, k) for k in overridden_keys],
                "validation_issues": structural_issues,
            }

            # 가정·계산 근거 탭: 큰 규모(없으면 작은 규모) 실행안 기준 상세 분석
            focus = next((o for o in computed if o["fm_count"] == max(
                (c["fm_count"] for c in computed), default=0)), None)
            if focus:
                pnl = focus["pnl"]
                sensitivity = run_full_sensitivity(focus["scenario"], region, reward_level,
                                                    assumptions, version, keys=DRIVER_CANDIDATE_KEYS)
                drivers = rank_drivers_by_swing(sensitivity, top_n=3)
                for d in drivers:
                    d["label"] = KEY_LABELS.get(d["key"], d["key"])
                basis_result = {
                    "scenario": focus["scenario"],
                    "pnl": pnl,
                    "drivers": drivers,
                    "reconcile_errors": pnl.reconcile(yakoo_config.RECONCILIATION_TOLERANCE),
                    "incremental_revenue": incremental_revenue(pnl),
                    "incremental_cac": compute_incremental_cac(pnl),
                    "using_overrides": using_overrides,
                    "overridden_keys": overridden_keys,
                    "validation_issues": structural_issues,
                }

    # 파일럿 탭 비교용으로 첫 화면 조건(지역/큰 규모 인원/보상비)을 그대로 넘겨받는다.
    pilot_region = regions.get(form_state["region_id"]) or (next(iter(regions.values())) if regions else None)
    try:
        pilot_fm_count = max(1, int(float(form_state["large_fm_count"])))
    except ValueError:
        pilot_fm_count = 10
    try:
        pilot_reward_cost = float(form_state["reward_cost"])
    except ValueError:
        pilot_reward_cost = default_reward_cost

    if form_name == "pilot":
        conv_file = request.files.get("conversion_file")
        rep_file = request.files.get("repeat_file")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        saved_paths = []
        try:
            if conv_file and conv_file.filename:
                p = UPLOAD_DIR / secure_filename(conv_file.filename)
                conv_file.save(p)
                saved_paths.append(("conversion", p))
            if rep_file and rep_file.filename:
                p = UPLOAD_DIR / secure_filename(rep_file.filename)
                rep_file.save(p)
                saved_paths.append(("repeat", p))

            if not saved_paths:
                pilot_result = {"error": "전환 실적 또는 재구매 실적 CSV 파일을 최소 1개 업로드해 주세요."}
            elif pilot_region is None:
                pilot_result = {"error": "비교에 사용할 지역이 없습니다."}
            else:
                ledger = load_ledger(LEDGER_PATH)
                ingest_log = []
                for kind, p in saved_paths:
                    if kind == "conversion":
                        ingest_log.append(ingest_conversion_file(p, ledger))
                    else:
                        ingest_log.append(ingest_repeat_file(p, ledger))
                save_ledger(ledger, LEDGER_PATH)

                conv_rates = compute_conversion_rates(ledger, pilot_as_of, yakoo_config.MIN_PILOT_SAMPLE_SIZE)
                repeat_rates = compute_repeat_purchase_rates(ledger, pilot_as_of, yakoo_config.MIN_PILOT_SAMPLE_SIZE)
                all_rates = {**conv_rates, **repeat_rates}
                updated_assumptions, applied, warnings = apply_rate_updates(base_assumptions, all_rates, pilot_as_of)
                applied_keys = {a["key"] for a in applied}

                rate_rows = []
                for key, est in all_rates.items():
                    old = base_assumptions.get(key)
                    kind = KEY_KIND.get(key, "ratio")
                    rate_rows.append({
                        "key": key, "label": KEY_LABELS.get(key, key),
                        "old_display": _display_str(old.value if old else None, kind),
                        "new_display": _display_str(est.value, kind),
                        "sample_size": est.sample_size,
                        "applied": key in applied_keys,
                    })

                comparison = None
                if applied:
                    reward_level = resolve_reward_level(pilot_reward_cost, reward_levels)
                    scenario = build_scenario(pilot_region, pilot_fm_count, reward_level)
                    before_pnl = compute_scenario_pnl(scenario, pilot_region, reward_level,
                                                       base_assumptions, f"{assumptions_file}@{as_of_date}")
                    after_pnl = compute_scenario_pnl(scenario, pilot_region, reward_level,
                                                      updated_assumptions, f"파일럿반영@{pilot_as_of}")
                    comparison = {"scenario": scenario, "before": before_pnl, "after": after_pnl}

                    out_path = INPUT_DIR / f"assumptions_dashboard_pilot_{pilot_as_of}.json"
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump({
                            "_comment": "대시보드 파일럿 실적 업로드 탭에서 생성됨. 가상 예제 데이터 기반입니다.",
                            "as_of_date": pilot_as_of,
                            "assumptions": [
                                {"key": a.key, "value": a.value, "unit": a.unit, "value_type": a.value_type,
                                 "source": a.source, "period": a.period, "notes": a.notes}
                                for a in updated_assumptions.values()
                            ],
                        }, f, ensure_ascii=False, indent=2)
                    assumption_files = list_assumption_files()

                # 업로드 직후의 실적으로 확대 기준 판정을 갱신한다.
                expansion_rows = build_expansion_rows(pilot_as_of)
                pilot_result = {
                    "error": None, "ingest_log": ingest_log, "rate_rows": rate_rows,
                    "warnings": warnings, "comparison": comparison, "as_of": pilot_as_of,
                }
        except Exception as exc:  # noqa: BLE001 - 업로드 파일 오류를 화면에 안내
            pilot_result = {"error": f"파일럿 실적 처리 중 오류가 발생했습니다: {exc}"}

    return render_template(
        "index.html",
        assumption_files=assumption_files,
        form_state=form_state,
        as_of_date=as_of_date,
        regions=regions,
        reward_levels=reward_levels,
        region_info_json=json.dumps(region_info, ensure_ascii=False),
        reward_presets_json=json.dumps(reward_presets, ensure_ascii=False),
        top_rows=top_rows,
        detail_rows=detail_rows,
        decision_result=decision_result,
        basis_result=basis_result,
        pilot_result=pilot_result,
        readiness_items=readiness_items,
        readiness=readiness,
        expansion_rows=expansion_rows,
        pilot_as_of=pilot_as_of,
        active_tab=active_tab,
        calc_version=yakoo_config.CALC_VERSION,
        random_seed=yakoo_config.RANDOM_SEED,
        band_names=BAND_NAMES,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
