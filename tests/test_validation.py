from yakoo_sim.calculator import compute_all_scenarios
from yakoo_sim.models import Assumption, Region, RewardLevel, Scenario
from yakoo_sim.validation import run_full_validation, validate_assumptions


def full_assumptions(overrides=None):
    base = {
        "conversion_rate_domestic_treatment": 0.20,
        "conversion_rate_tourist_treatment": 0.10,
        "conversion_rate_domestic_control": 0.10,
        "conversion_rate_tourist_control": 0.05,
        "avg_order_value_domestic": 40000.0,
        "avg_order_value_tourist": 30000.0,
        "repeat_purchase_rate_domestic": 0.25,
        "avg_repeat_orders_per_repeat_customer_domestic": 2.0,
        "regular_promo_cost_per_conversion": 5000.0,
        "delivery_cost_per_order_domestic": 3000.0,
        "initial_production_cost_program": 1000000.0,
        "conversion_observation_window_days": 7,
        "repeat_purchase_observation_window_days": 90,
    }
    if overrides:
        base.update(overrides)
    return {
        k: Assumption(key=k, value=v, unit="", value_type="가정", source="test", period="2026")
        for k, v in base.items()
    }


def test_validate_assumptions_passes_for_complete_input():
    issues = validate_assumptions(full_assumptions())
    assert issues == []


def test_validate_assumptions_flags_missing_key():
    assumptions = full_assumptions()
    del assumptions["avg_order_value_domestic"]
    issues = validate_assumptions(assumptions)
    assert any(i.rule == "required_assumption_missing" for i in issues)


def test_validate_assumptions_flags_missing_source():
    assumptions = full_assumptions()
    assumptions["avg_order_value_domestic"].source = ""
    issues = validate_assumptions(assumptions)
    assert any(i.rule == "assumption_metadata_missing" for i in issues)


def test_validate_assumptions_flags_ratio_out_of_range():
    assumptions = full_assumptions({"conversion_rate_domestic_treatment": 1.5})
    issues = validate_assumptions(assumptions)
    assert any(i.rule == "ratio_out_of_range" for i in issues)


def test_full_validation_blocks_expansion_on_critical_failure():
    assumptions = full_assumptions()
    del assumptions["initial_production_cost_program"]  # 치명적 누락
    region = Region(region_id="r1", region_name="테스트", tourist_share=0.5,
                     contacted_customers_per_fm=100, fixed_operation_cost_per_fm=1000,
                     value_type="가정", source="t", period="2026")
    reward_level = RewardLevel(reward_level_id="mid", label="중", reward_cost_per_conversion=8000,
                                value_type="가정", source="t", period="2026")
    scenario = Scenario(scenario_id="s1", region_id="r1", fm_count=5, reward_level_id="mid", label="테스트")

    # 계산 자체는 필수 가정 누락 시 KeyError로 실패하므로, 검증은 계산 이전 단계에서 걸러야 한다.
    report = run_full_validation(assumptions, {"r1": region}, {"mid": reward_level}, [scenario], [])
    assert report.has_critical
    assert report.expansion_recommendation_allowed is False


def test_full_validation_allows_expansion_when_clean():
    assumptions = full_assumptions()
    region = Region(region_id="r1", region_name="테스트", tourist_share=0.5,
                     contacted_customers_per_fm=100, fixed_operation_cost_per_fm=1000,
                     value_type="가정", source="t", period="2026")
    reward_level = RewardLevel(reward_level_id="mid", label="중", reward_cost_per_conversion=8000,
                                value_type="가정", source="t", period="2026")
    scenario = Scenario(scenario_id="s1", region_id="r1", fm_count=5, reward_level_id="mid", label="테스트")
    results = compute_all_scenarios([scenario], {"r1": region}, {"mid": reward_level}, assumptions, "v1")

    report = run_full_validation(assumptions, {"r1": region}, {"mid": reward_level}, [scenario], results)
    assert report.expansion_recommendation_allowed is True


def test_referential_integrity_failure_detected():
    assumptions = full_assumptions()
    region = Region(region_id="r1", region_name="테스트", tourist_share=0.5,
                     contacted_customers_per_fm=100, fixed_operation_cost_per_fm=1000,
                     value_type="가정", source="t", period="2026")
    reward_level = RewardLevel(reward_level_id="mid", label="중", reward_cost_per_conversion=8000,
                                value_type="가정", source="t", period="2026")
    bad_scenario = Scenario(scenario_id="s1", region_id="nonexistent", fm_count=5,
                             reward_level_id="mid", label="테스트")
    report = run_full_validation(assumptions, {"r1": region}, {"mid": reward_level}, [bad_scenario], [])
    assert any(i.rule == "referential_integrity" for i in report.issues)
