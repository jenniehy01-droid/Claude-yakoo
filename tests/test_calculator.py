from yakoo_sim.calculator import compute_scenario_pnl
from yakoo_sim.models import Assumption, Region, RewardLevel, Scenario


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
    return Region(
        region_id="r1", region_name="테스트지역", tourist_share=0.5,
        contacted_customers_per_fm=100, fixed_operation_cost_per_fm=10000,
        value_type="가정", source="test", period="2026",
    )


def make_scenario(fm_count=10):
    return Scenario(scenario_id="s1", region_id="r1", fm_count=fm_count, reward_level_id="mid", label="테스트")


def make_reward_level(cost=8000.0):
    return RewardLevel(reward_level_id="mid", label="중", reward_cost_per_conversion=cost,
                        value_type="가정", source="test", period="2026")


def test_contacted_split_by_tourist_share():
    region = make_region()
    scenario = make_scenario(fm_count=10)
    pnl = compute_scenario_pnl(scenario, region, make_reward_level(), make_assumptions(), "v1")
    contacted_total = 10 * 100
    assert pnl.treatment.contacted_total == contacted_total
    assert pnl.treatment.contacted_tourist == contacted_total * 0.5
    assert pnl.treatment.contacted_domestic == contacted_total * 0.5


def test_revenue_and_cost_hand_calculation():
    region = make_region()
    scenario = make_scenario(fm_count=1)  # contacted_total = 100
    assumptions = make_assumptions()
    reward_level = make_reward_level(cost=8000.0)
    pnl = compute_scenario_pnl(scenario, region, reward_level, assumptions, "v1")

    t = pnl.treatment
    # contacted: tourist=50, domestic=50
    expected_new_tourist = 50 * 0.10
    expected_new_domestic = 50 * 0.20
    assert t.new_customers_tourist == expected_new_tourist
    assert t.new_customers_domestic == expected_new_domestic

    repeat_multiplier = 1 + 0.25 * 2.0  # 1.5
    expected_revenue_tourist = expected_new_tourist * 30000.0
    expected_revenue_domestic = expected_new_domestic * 40000.0 * repeat_multiplier
    assert abs(t.revenue_tourist - expected_revenue_tourist) < 1e-9
    assert abs(t.revenue_domestic - expected_revenue_domestic) < 1e-9

    expected_acq_cost = (expected_new_tourist + expected_new_domestic) * 8000.0
    expected_delivery_cost = expected_new_domestic * repeat_multiplier * 3000.0
    expected_fixed_cost = 1 * 10000
    assert abs(t.acquisition_cost - expected_acq_cost) < 1e-9
    assert abs(t.delivery_cost - expected_delivery_cost) < 1e-9
    assert abs(t.fixed_cost - expected_fixed_cost) < 1e-9

    expected_profit_excl = (expected_revenue_tourist + expected_revenue_domestic) - \
        (expected_acq_cost + expected_delivery_cost + expected_fixed_cost)
    assert abs(t.profit_excl_initial - expected_profit_excl) < 1e-9
    assert abs(t.profit_incl_initial - (expected_profit_excl - 1000000.0)) < 1e-9


def test_control_group_has_no_initial_cost():
    region = make_region()
    scenario = make_scenario(fm_count=1)
    pnl = compute_scenario_pnl(scenario, region, make_reward_level(), make_assumptions(), "v1")
    assert pnl.control.initial_cost_applied == 0.0
    assert pnl.control.profit_incl_initial == pnl.control.profit_excl_initial


def test_incremental_profit_matches_difference():
    region = make_region()
    scenario = make_scenario(fm_count=5)
    pnl = compute_scenario_pnl(scenario, region, make_reward_level(), make_assumptions(), "v1")
    assert abs(pnl.incremental_profit_excl_initial -
               (pnl.treatment.profit_excl_initial - pnl.control.profit_excl_initial)) < 1e-9
    assert abs(pnl.incremental_profit_incl_initial -
               (pnl.treatment.profit_incl_initial - pnl.control.profit_incl_initial)) < 1e-9


def test_reconcile_passes_on_valid_result():
    region = make_region()
    scenario = make_scenario(fm_count=5)
    pnl = compute_scenario_pnl(scenario, region, make_reward_level(), make_assumptions(), "v1")
    assert pnl.reconcile(1e-6) == []


def test_missing_assumption_raises():
    region = make_region()
    scenario = make_scenario(fm_count=5)
    assumptions = make_assumptions()
    del assumptions["avg_order_value_domestic"]
    try:
        compute_scenario_pnl(scenario, region, make_reward_level(), assumptions, "v1")
        assert False, "should have raised"
    except KeyError:
        pass


def test_higher_conversion_rate_increases_revenue():
    region = make_region()
    scenario = make_scenario(fm_count=5)
    base = compute_scenario_pnl(scenario, region, make_reward_level(),
                                 make_assumptions(), "v1")
    higher = compute_scenario_pnl(scenario, region, make_reward_level(),
                                   make_assumptions({"conversion_rate_domestic_treatment": 0.30}), "v1")
    assert higher.treatment.revenue_domestic > base.treatment.revenue_domestic
