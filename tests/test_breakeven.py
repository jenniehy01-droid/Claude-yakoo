from yakoo_sim.breakeven import solve_breakeven_assumption, solve_breakeven_reward_cost
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
    return {k: Assumption(key=k, value=v, unit="", value_type="가정", source="test", period="2026")
            for k, v in base.items()}


def make_region():
    return Region(region_id="r1", region_name="테스트지역", tourist_share=0.5,
                   contacted_customers_per_fm=100, fixed_operation_cost_per_fm=10000,
                   value_type="가정", source="test", period="2026")


def make_scenario(fm_count=10):
    return Scenario(scenario_id="s1", region_id="r1", fm_count=fm_count,
                     reward_level_id="mid", label="테스트")


def make_reward_level(cost=8000.0):
    return RewardLevel(reward_level_id="mid", label="중", reward_cost_per_conversion=cost,
                        value_type="가정", source="test", period="2026")


def test_breakeven_conversion_rate_makes_incremental_profit_zero():
    region, scenario, reward = make_region(), make_scenario(), make_reward_level()
    assumptions = make_assumptions()
    result = solve_breakeven_assumption(
        scenario, region, reward, assumptions,
        "conversion_rate_domestic_treatment", "첫 구매율", lo=0.0, hi=1.0, include_initial=True)

    assert result.breakeven_value is not None
    assert result.unavailable_reason is None
    # 찾은 값을 실제로 넣으면 추가손익(초기비용 포함)이 0에 수렴해야 한다
    probe = dict(assumptions)
    key = "conversion_rate_domestic_treatment"
    probe[key] = Assumption(key=key, value=result.breakeven_value, unit="", value_type="가정",
                             source="t", period="2026")
    pnl = compute_scenario_pnl(scenario, region, reward, probe, "v")
    assert abs(pnl.incremental_profit_incl_initial) < 1.0  # 1원 미만 오차
    assert result.gap == result.breakeven_value - assumptions[key].value


def test_breakeven_reward_cost_makes_incremental_profit_zero():
    region, scenario = make_region(), make_scenario()
    assumptions = make_assumptions()
    reward = make_reward_level(cost=8000.0)
    result = solve_breakeven_reward_cost(scenario, region, reward, assumptions, include_initial=True)

    assert result.breakeven_value is not None
    probe_reward = make_reward_level(cost=result.breakeven_value)
    pnl = compute_scenario_pnl(scenario, region, probe_reward, assumptions, "v")
    assert abs(pnl.incremental_profit_incl_initial) < 1.0


def test_breakeven_returns_reason_when_always_loss_in_range():
    """초기 제작비가 매우 커서 재구매율만으로는 손익분기에 도달할 수 없는 경우 (항상 손실)."""
    region, scenario, reward = make_region(), make_scenario(), make_reward_level()
    assumptions = make_assumptions({"initial_production_cost_program": 10_000_000_000.0})
    result = solve_breakeven_assumption(
        scenario, region, reward, assumptions,
        "repeat_purchase_rate_domestic", "재구매율", lo=0.0, hi=1.0, include_initial=True)

    assert result.breakeven_value is None
    assert result.gap is None
    assert result.unavailable_reason is not None
    assert result.endpoints_sign == "always_loss"


def test_breakeven_distinguishes_always_profit_from_always_loss():
    """범위 전체가 이익인 경우와 손실인 경우를 구분해야 한다 — 해석이 정반대이기 때문."""
    region, scenario, reward = make_region(), make_scenario(), make_reward_level()

    # 초기 제작비를 0으로 두면 재구매율이 0이어도 이익 -> always_profit
    profitable = make_assumptions({"initial_production_cost_program": 0.0})
    result_profit = solve_breakeven_assumption(
        scenario, region, reward, profitable,
        "repeat_purchase_rate_domestic", "재구매율", lo=0.0, hi=1.0, include_initial=True)
    assert result_profit.breakeven_value is None
    assert result_profit.endpoints_sign == "always_profit"

    # 초기 제작비를 매우 크게 두면 항상 손실 -> always_loss
    unprofitable = make_assumptions({"initial_production_cost_program": 10_000_000_000.0})
    result_loss = solve_breakeven_assumption(
        scenario, region, reward, unprofitable,
        "repeat_purchase_rate_domestic", "재구매율", lo=0.0, hi=1.0, include_initial=True)
    assert result_loss.endpoints_sign == "always_loss"


def test_breakeven_missing_assumption_key_is_reported():
    region, scenario, reward = make_region(), make_scenario(), make_reward_level()
    assumptions = make_assumptions()
    del assumptions["repeat_purchase_rate_domestic"]
    result = solve_breakeven_assumption(
        scenario, region, reward, assumptions,
        "repeat_purchase_rate_domestic", "재구매율", lo=0.0, hi=1.0)
    assert result.breakeven_value is None
    assert "입력되지 않아" in result.unavailable_reason
