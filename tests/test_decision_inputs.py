from pathlib import Path

from yakoo_sim.decision_inputs import (
    ExpansionCriterion,
    ReadinessItem,
    evaluate_expansion_criterion,
    get_readiness_value,
    load_decision_readiness,
    load_expansion_criteria,
    pilot_conversion_gap_pp,
    readiness_summary,
)
from yakoo_sim.pilot_update import RateEstimate

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = REPO_ROOT / "data" / "input"


def test_load_decision_readiness_from_example_file():
    items = load_decision_readiness(INPUT_DIR / "decision_readiness.csv")
    ids = {i.item_id for i in items}
    assert {"product_margin", "operation_quote", "loss_tolerance",
            "manager_capacity", "sample_design"} <= ids


def test_readiness_summary_blocks_recommendation_when_not_all_confirmed():
    items = [
        ReadinessItem("a", "항목A", "확보", 1.0, "원", "정산서", ""),
        ReadinessItem("b", "항목B", "입력필요", None, "", "", ""),
    ]
    summary = readiness_summary(items)
    assert summary["recommendation_allowed"] is False
    assert summary["confirmed"] == 1
    assert [i.item_id for i in summary["missing"]] == ["b"]


def test_readiness_summary_allows_when_all_confirmed():
    items = [
        ReadinessItem("a", "항목A", "확보", 1.0, "원", "정산서", ""),
        ReadinessItem("b", "항목B", "확보", 2.0, "원", "견적서", ""),
    ]
    assert readiness_summary(items)["recommendation_allowed"] is True


def test_example_readiness_file_blocks_recommendation():
    """가상 예제 데이터는 근거가 갖춰지지 않은 상태이므로 투자 추천이 보류되어야 한다."""
    items = load_decision_readiness(INPUT_DIR / "decision_readiness.csv")
    assert readiness_summary(items)["recommendation_allowed"] is False


def test_get_readiness_value_returns_none_for_unentered_item():
    items = load_decision_readiness(INPUT_DIR / "decision_readiness.csv")
    assert get_readiness_value(items, "loss_tolerance") is None  # 허용 손실 한도 미입력
    assert get_readiness_value(items, "operation_quote") == 900000


def test_load_expansion_criteria_from_example_file():
    criteria = load_expansion_criteria(INPUT_DIR / "expansion_criteria.csv")
    ids = {c.criterion_id for c in criteria}
    assert {"incremental_purchase", "repeat_30d", "actual_cost", "delivery_impact"} <= ids
    measurable = [c for c in criteria if c.is_measurable]
    assert [c.criterion_id for c in measurable] == ["incremental_purchase"]


def test_evaluate_expansion_criterion_directions():
    up = ExpansionCriterion("c1", "추가 구매", "정의", 5, "%p", "이상", "m", "")
    assert evaluate_expansion_criterion(up, 6.0)["judgement"] == "충족"
    assert evaluate_expansion_criterion(up, 4.0)["judgement"] == "미달"
    assert evaluate_expansion_criterion(up, None)["judgement"] == "미측정"

    down = ExpansionCriterion("c2", "실제 비용", "정의", 8000, "원", "이하", "m", "")
    assert evaluate_expansion_criterion(down, 7000.0)["judgement"] == "충족"
    assert evaluate_expansion_criterion(down, 9000.0)["judgement"] == "미달"


def test_pilot_conversion_gap_pp():
    rates = {
        "conversion_rate_domestic_treatment": RateEstimate(
            "conversion_rate_domestic_treatment", 0.18, 100, 18, "2026-09-01", True),
        "conversion_rate_domestic_control": RateEstimate(
            "conversion_rate_domestic_control", 0.10, 100, 10, "2026-09-01", True),
    }
    assert abs(pilot_conversion_gap_pp(rates) - 8.0) < 1e-9


def test_pilot_conversion_gap_none_when_sample_missing():
    rates = {
        "conversion_rate_domestic_treatment": RateEstimate(
            "conversion_rate_domestic_treatment", None, 0, 0, "2026-09-01", False),
        "conversion_rate_domestic_control": RateEstimate(
            "conversion_rate_domestic_control", 0.10, 100, 10, "2026-09-01", True),
    }
    assert pilot_conversion_gap_pp(rates) is None
