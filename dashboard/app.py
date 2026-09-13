"""야쿠헌터즈 사업성 시뮬레이션 — 로컬 대시보드 (MBA 발표용 화면).

중요: 이 대시보드는 손익 계산식을 직접 구현하지 않는다. 모든 계산은
`src/yakoo_sim` 의 검증된(pytest로 테스트된) 계산기 함수를 그대로 호출한
결과만 사용한다:
  - yakoo_sim.calculator.compute_scenario_pnl / incremental_revenue / compute_incremental_cac
  - yakoo_sim.scenarios.compute_scenario_bands / run_full_sensitivity / rank_drivers_by_swing
  - yakoo_sim.validation.validate_assumptions / ScenarioPnL.reconcile
  - yakoo_sim.pilot_update.* (파일럿 업로드 탭에서 그대로 재사용 — 중복방지 ledger 포함)

로컬 전용, 오프라인 실행:
  - Flask 개발 서버로 로컬(127.0.0.1)에서만 구동한다. 외부 API/DB 연결 없음.
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
from yakoo_sim.calculator import (  # noqa: E402
    compute_incremental_cac,
    compute_scenario_pnl,
    incremental_revenue,
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


# ---------------------------------------------------------------------------
# 서식 필터 — 금액은 원/만원 단위를 명확히 하고, 이익/손실은 부호+문구로 구분한다.
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
    sign = "+" if v >= 0 else "-"
    return f"{sign}{abs(v) / 10000:,.0f}만원"


# ---------------------------------------------------------------------------
# 가정값 항목 정의 — key, 표시라벨, 종류(ratio=%로 표시/krw=원/count=횟수),
# 화면 배치 위치(top=좌측 상단 핵심입력 / detail=상세설정 접기), 분모 설명(비율만).
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

# 하단 "핵심 변수 3개" 랭킹에 포함할 후보 (민감도 분석 대상)
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


def render_band_chart(bands: dict) -> str:
    """보수/중간/낙관 밴드별로 일반판촉 vs 야쿠헌터즈 이익(초기제작비 제외)을 비교한다."""
    band_names = [name for name, _ in BAND_DEFINITIONS]
    treatment_vals = [bands[name].treatment.profit_excl_initial / 10000 for name in band_names]
    control_vals = [bands[name].control.profit_excl_initial / 10000 for name in band_names]

    x = range(len(band_names))
    width = 0.32

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.bar([i - width / 2 for i in x], control_vals, width=width, label="일반판촉", color="#9aa3a0")
    ax.bar([i + width / 2 for i in x], treatment_vals, width=width, label="야쿠헌터즈", color="#0f5132")
    ax.axhline(0, color="#666", linewidth=1)
    ax.set_ylabel("이익 (초기제작비 제외, 만원)")
    ax.set_title("시나리오별 손익 비교: 일반판촉 vs 야쿠헌터즈")
    ax.set_xticks(list(x))
    ax.set_xticklabels(band_names, fontsize=13)
    ax.legend(loc="upper left", frameon=False)
    fig.tight_layout()
    return fig_to_base64()


def build_focus_scenario(region, fm_count, reward_level) -> Scenario:
    return Scenario(
        scenario_id="dashboard_custom", region_id=region.region_id,
        fm_count=fm_count, reward_level_id=reward_level.reward_level_id,
        label=f"{region.region_name} · FM {fm_count}명 · 보상비 {reward_level.reward_cost_per_conversion:,.0f}원",
    )


def compute_focus_result(scenario, region, reward_level, assumptions, version) -> dict:
    pnl = compute_scenario_pnl(scenario, region, reward_level, assumptions, version)
    reconcile_errors = pnl.reconcile(yakoo_config.RECONCILIATION_TOLERANCE)
    bands = compute_scenario_bands(scenario, region, reward_level, assumptions, version)
    sensitivity = run_full_sensitivity(scenario, region, reward_level, assumptions, version,
                                        keys=DRIVER_CANDIDATE_KEYS)
    drivers = rank_drivers_by_swing(sensitivity, top_n=3)
    for d in drivers:
        d["label"] = KEY_LABELS.get(d["key"], d["key"])
    return {
        "pnl": pnl,
        "reconcile_errors": reconcile_errors,
        "incremental_revenue": incremental_revenue(pnl),
        "incremental_cac": compute_incremental_cac(pnl),
        "bands": bands,
        "chart_b64": render_band_chart(bands),
        "drivers": drivers,
    }


@app.route("/", methods=["GET", "POST"])
def index():
    assumption_files = list_assumption_files()
    default_assumptions_file = assumption_files[0][0] if assumption_files else None
    form_name = request.form.get("form_name") if request.method == "POST" else None
    active_tab = "pilot" if form_name == "pilot" else "simulate"

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
        "fm_count": request.form.get("fm_count", "10"),
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

    sim_result = None
    pilot_result = None

    if form_name == "simulate":
        try:
            fm_count = max(1, int(float(form_state["fm_count"])))
        except ValueError:
            fm_count = 1
        try:
            reward_cost = float(form_state["reward_cost"])
        except ValueError:
            reward_cost = default_reward_cost
        region = regions.get(form_state["region_id"])

        if region is None:
            sim_result = {"error": "지역을 선택해 주세요."}
        else:
            base_with_overrides, overridden_keys = apply_overrides(base_assumptions, request.form)
            all_issues = validate_assumptions(base_with_overrides)
            structural_issues = [
                i for i in all_issues
                if not (i.rule == "assumption_metadata_missing" and any(k in i.message for k in overridden_keys))
            ]
            using_overrides = bool(overridden_keys)
            reward_level = resolve_reward_level(reward_cost, reward_levels)
            scenario = build_focus_scenario(region, fm_count, reward_level)
            version = f"{assumptions_file}@{as_of_date}"

            focus = compute_focus_result(scenario, region, reward_level, base_with_overrides, version)
            expansion_allowed = (not using_overrides and not structural_issues
                                  and not focus["reconcile_errors"])

            sim_result = {
                "error": None,
                "region": region, "fm_count": fm_count, "reward_level": reward_level,
                "scenario": scenario,
                "overridden_keys": overridden_keys,
                "overridden_labels": [KEY_LABELS.get(k, k) for k in overridden_keys],
                "using_overrides": using_overrides,
                "validation_issues": structural_issues,
                "expansion_allowed": expansion_allowed,
                **focus,
            }

    # 파일럿 탭 비교용으로 시뮬레이터 조건(지역/인원/보상비)을 그대로 넘겨받는다.
    pilot_region = regions.get(form_state["region_id"]) or (next(iter(regions.values())) if regions else None)
    try:
        pilot_fm_count = max(1, int(float(form_state["fm_count"])))
    except ValueError:
        pilot_fm_count = 10
    try:
        pilot_reward_cost = float(form_state["reward_cost"])
    except ValueError:
        pilot_reward_cost = default_reward_cost

    pilot_as_of = request.form.get("as_of_date", date.today().isoformat())

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
                    scenario = build_focus_scenario(pilot_region, pilot_fm_count, reward_level)
                    before_pnl = compute_scenario_pnl(scenario, pilot_region, reward_level,
                                                       base_assumptions, f"{assumptions_file}@{as_of_date}")
                    after_pnl = compute_scenario_pnl(scenario, pilot_region, reward_level,
                                                      updated_assumptions, f"파일럿반영@{pilot_as_of}")
                    comparison = {
                        "scenario": scenario,
                        "before": before_pnl, "after": after_pnl,
                        "before_incremental_cac": compute_incremental_cac(before_pnl),
                        "after_incremental_cac": compute_incremental_cac(after_pnl),
                    }

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

                pilot_result = {
                    "error": None,
                    "ingest_log": ingest_log,
                    "rate_rows": rate_rows,
                    "warnings": warnings,
                    "comparison": comparison,
                    "as_of": pilot_as_of,
                }
        except Exception as exc:  # noqa: BLE001 - 사용자 업로드 파일 오류를 화면에 안내
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
        sim_result=sim_result,
        pilot_result=pilot_result,
        pilot_as_of=pilot_as_of,
        active_tab=active_tab,
        calc_version=yakoo_config.CALC_VERSION,
        random_seed=yakoo_config.RANDOM_SEED,
        band_names=[name for name, _ in BAND_DEFINITIONS],
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
