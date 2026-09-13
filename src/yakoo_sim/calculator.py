"""손익 계산 엔진.

docs/requirements.md 4절의 계산식을 그대로 구현한다. 이 모듈은 난수를
전혀 사용하지 않는 완전 결정론적 계산이다 (근거 없는 확률/전환율을
자동으로 만들지 않는다는 필수 규칙).
"""
from __future__ import annotations

from .config import CALC_VERSION
from .models import Assumption, GroupPnL, Region, RewardLevel, Scenario, ScenarioPnL


def _get(assumptions: dict[str, Assumption], key: str) -> float:
    if key not in assumptions:
        raise KeyError(f"필수 가정값 누락: {key}")
    return assumptions[key].value


def compute_scenario_pnl(
    scenario: Scenario,
    region: Region,
    reward_level: RewardLevel,
    assumptions: dict[str, Assumption],
    assumptions_version: str,
) -> ScenarioPnL:
    contacted_total = scenario.fm_count * region.contacted_customers_per_fm
    contacted_tourist = contacted_total * region.tourist_share
    contacted_domestic = contacted_total * (1 - region.tourist_share)

    repeat_rate = _get(assumptions, "repeat_purchase_rate_domestic")
    avg_repeat_orders = _get(assumptions, "avg_repeat_orders_per_repeat_customer_domestic")
    repeat_multiplier = 1 + repeat_rate * avg_repeat_orders

    avg_ov_domestic = _get(assumptions, "avg_order_value_domestic")
    avg_ov_tourist = _get(assumptions, "avg_order_value_tourist")
    delivery_cost_per_order = _get(assumptions, "delivery_cost_per_order_domestic")
    fixed_cost = scenario.fm_count * region.fixed_operation_cost_per_fm

    def build_group(group: str, variable_unit_cost: float, initial_cost_applied: float) -> GroupPnL:
        conv_tourist = _get(assumptions, f"conversion_rate_tourist_{group}")
        conv_domestic = _get(assumptions, f"conversion_rate_domestic_{group}")

        new_tourist = contacted_tourist * conv_tourist
        new_domestic = contacted_domestic * conv_domestic

        revenue_tourist = new_tourist * avg_ov_tourist
        revenue_domestic = new_domestic * avg_ov_domestic * repeat_multiplier
        revenue_total = revenue_tourist + revenue_domestic

        acquisition_cost = (new_tourist + new_domestic) * variable_unit_cost
        delivery_cost = new_domestic * repeat_multiplier * delivery_cost_per_order
        cost_excl_initial = acquisition_cost + delivery_cost + fixed_cost

        profit_excl_initial = revenue_total - cost_excl_initial
        profit_incl_initial = profit_excl_initial - initial_cost_applied

        return GroupPnL(
            group=group,
            contacted_total=contacted_tourist + contacted_domestic,
            contacted_tourist=contacted_tourist,
            contacted_domestic=contacted_domestic,
            new_customers_tourist=new_tourist,
            new_customers_domestic=new_domestic,
            revenue_tourist=revenue_tourist,
            revenue_domestic=revenue_domestic,
            revenue_total=revenue_total,
            acquisition_cost=acquisition_cost,
            delivery_cost=delivery_cost,
            fixed_cost=fixed_cost,
            cost_excl_initial=cost_excl_initial,
            profit_excl_initial=profit_excl_initial,
            initial_cost_applied=initial_cost_applied,
            profit_incl_initial=profit_incl_initial,
        )

    initial_cost = _get(assumptions, "initial_production_cost_program")
    regular_promo_cost = _get(assumptions, "regular_promo_cost_per_conversion")

    treatment = build_group("treatment", reward_level.reward_cost_per_conversion, initial_cost)
    control = build_group("control", regular_promo_cost, 0.0)

    incremental_excl = treatment.profit_excl_initial - control.profit_excl_initial
    incremental_incl = treatment.profit_incl_initial - control.profit_incl_initial

    return ScenarioPnL(
        scenario_id=scenario.scenario_id,
        region_id=region.region_id,
        reward_level_id=reward_level.reward_level_id,
        label=scenario.label,
        treatment=treatment,
        control=control,
        incremental_profit_excl_initial=incremental_excl,
        incremental_profit_incl_initial=incremental_incl,
        assumptions_version=assumptions_version,
        calc_version=CALC_VERSION,
    )


def incremental_revenue(pnl: ScenarioPnL) -> float:
    """야쿠헌터즈(실험군) 매출 - 일반판촉(비교군) 매출. 두 그룹 모두 이미
    compute_scenario_pnl 이 계산한 값이므로 새 손익 공식이 아니라 그 차이만
    반환한다."""
    return pnl.treatment.revenue_total - pnl.control.revenue_total


def compute_incremental_cac(pnl: ScenarioPnL) -> float | None:
    """증분 CAC(고객 1명 추가 획득당 순증 비용).

    (야쿠헌터즈 비용 - 일반판촉 비용) / (야쿠헌터즈 신규고객수 - 일반판촉 신규고객수)

    야쿠헌터즈가 일반판촉보다 신규 고객을 더 많이 확보하지 못하면(분모가 0
    이하) 정의되지 않으므로 None을 반환한다 — 억지로 계산해 오해를 부르는
    숫자를 만들지 않는다.
    """
    treatment_customers = pnl.treatment.new_customers_tourist + pnl.treatment.new_customers_domestic
    control_customers = pnl.control.new_customers_tourist + pnl.control.new_customers_domestic
    delta_customers = treatment_customers - control_customers
    if delta_customers <= 0:
        return None
    delta_cost = pnl.treatment.cost_excl_initial - pnl.control.cost_excl_initial
    return delta_cost / delta_customers


def compute_all_scenarios(
    scenarios: list[Scenario],
    regions: dict[str, Region],
    reward_levels: dict[str, RewardLevel],
    assumptions: dict[str, Assumption],
    assumptions_version: str,
) -> list[ScenarioPnL]:
    results = []
    for sc in scenarios:
        region = regions[sc.region_id]
        reward_level = reward_levels[sc.reward_level_id]
        results.append(compute_scenario_pnl(sc, region, reward_level, assumptions, assumptions_version))
    return results
