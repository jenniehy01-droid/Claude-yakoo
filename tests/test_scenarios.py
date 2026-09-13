from yakoo_sim.calculator import compute_scenario_pnl
from yakoo_sim.models import Assumption, Region, RewardLevel, Scenario
from yakoo_sim.scenarios import (
    BAND_DEFINITIONS,
    compute_scenario_bands,
    rank_drivers_by_swing,
    run_full_sensitivity,
)


def make_assumptions(overrides=None):
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


def make_region():
    return Region(region_id="r1", region_name="테스트지역", tourist_share=0.5,
                   contacted_customers_per_fm=100, fixed_operation_cost_per_fm=10000,
                   value_type="가정", source="test", period="2026")


def make_scenario(fm_count=10):
    return Scenario(scenario_id="s1", region_id="r1", fm_count=fm_count, reward_level_id="mid", label="테스트")


def make_reward_level(cost=8000.0):
    return RewardLevel(reward_level_id="mid", label="중", reward_cost_per_conversion=cost,
                        value_type="가정", source="test", period="2026")


def test_scenario_bands_are_ordered_conservative_to_optimistic():
    region, scenario, reward_level = make_region(), make_scenario(), make_reward_level()
    assumptions = make_assumptions()
    bands = compute_scenario_bands(scenario, region, reward_level, assumptions, "v1")
    assert set(bands.keys()) == {name for name, _ in BAND_DEFINITIONS}
    conservative = bands["보수"].incremental_profit_excl_initial
    middle = bands["중간"].incremental_profit_excl_initial
    optimistic = bands["낙관"].incremental_profit_excl_initial
    assert conservative < middle < optimistic


def test_middle_band_matches_unmodified_assumptions():
    region, scenario, reward_level = make_region(), make_scenario(), make_reward_level()
    assumptions = make_assumptions()
    bands = compute_scenario_bands(scenario, region, reward_level, assumptions, "v1")
    baseline = compute_scenario_pnl(scenario, region, reward_level, assumptions, "v1")
    assert abs(bands["중간"].incremental_profit_excl_initial - baseline.incremental_profit_excl_initial) < 1e-9


def test_rank_drivers_by_swing_orders_by_impact():
    region, scenario, reward_level = make_region(), make_scenario(), make_reward_level()
    assumptions = make_assumptions()
    sensitivity = run_full_sensitivity(scenario, region, reward_level, assumptions, "v1")
    ranked = rank_drivers_by_swing(sensitivity, top_n=2)
    assert len(ranked) == 2
    # swing이 내림차순으로 정렬되어야 함
    assert ranked[0]["swing"] >= ranked[1]["swing"]
    for row in ranked:
        assert row["swing"] == row["max_incremental_profit"] - row["min_incremental_profit"]
