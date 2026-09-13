"""시나리오 비교 및 민감도 분석.

민감도 분석은 지정된 가정값을 결정론적 격자(예: -20%~+20%, 10% 간격)로
흔들어 재계산하는 방식만 사용한다. 확률분포에서 표본을 뽑는 방식(Monte
Carlo 등)은 근거 없는 확률을 만들어내지 않는다는 필수 규칙에 따라 1차
개발 범위에서 제외한다.
"""
from __future__ import annotations

from copy import deepcopy

from .calculator import compute_scenario_pnl
from .models import Assumption, Region, RewardLevel, Scenario, ScenarioPnL

DEFAULT_SENSITIVITY_DELTAS = (-0.20, -0.10, 0.0, 0.10, 0.20)

SENSITIVITY_KEYS = (
    "conversion_rate_domestic_treatment",
    "conversion_rate_tourist_treatment",
    "repeat_purchase_rate_domestic",
    "avg_repeat_orders_per_repeat_customer_domestic",
)


def rank_scenarios_by_incremental_profit(results: list[ScenarioPnL], include_initial: bool = False):
    key = (lambda r: r.incremental_profit_incl_initial) if include_initial else (
        lambda r: r.incremental_profit_excl_initial)
    return sorted(results, key=key, reverse=True)


def run_sensitivity_for_scenario(
    scenario: Scenario,
    region: Region,
    reward_level: RewardLevel,
    base_assumptions: dict[str, Assumption],
    assumptions_version: str,
    vary_key: str,
    deltas: tuple[float, ...] = DEFAULT_SENSITIVITY_DELTAS,
) -> list[dict]:
    if vary_key not in base_assumptions:
        raise KeyError(f"민감도 분석 대상 키가 assumptions에 없음: {vary_key}")

    base_value = base_assumptions[vary_key].value
    rows = []
    for delta in deltas:
        assumptions = deepcopy(base_assumptions)
        varied_value = base_value * (1 + delta)
        assumptions[vary_key] = Assumption(
            key=vary_key, value=varied_value, unit=base_assumptions[vary_key].unit,
            value_type=base_assumptions[vary_key].value_type,
            source=base_assumptions[vary_key].source + f" (민감도 조정 {delta:+.0%})",
            period=base_assumptions[vary_key].period,
        )
        pnl = compute_scenario_pnl(scenario, region, reward_level, assumptions, assumptions_version)
        rows.append({
            "vary_key": vary_key,
            "delta": delta,
            "value": varied_value,
            "incremental_profit_excl_initial": pnl.treatment.profit_excl_initial - pnl.control.profit_excl_initial,
            "incremental_profit_incl_initial": pnl.treatment.profit_incl_initial - pnl.control.profit_incl_initial,
            "treatment_profit_excl_initial": pnl.treatment.profit_excl_initial,
            "control_profit_excl_initial": pnl.control.profit_excl_initial,
        })
    return rows


def run_full_sensitivity(
    scenario: Scenario,
    region: Region,
    reward_level: RewardLevel,
    base_assumptions: dict[str, Assumption],
    assumptions_version: str,
    keys: tuple[str, ...] = SENSITIVITY_KEYS,
    deltas: tuple[float, ...] = DEFAULT_SENSITIVITY_DELTAS,
) -> dict[str, list[dict]]:
    return {
        key: run_sensitivity_for_scenario(
            scenario, region, reward_level, base_assumptions, assumptions_version, key, deltas
        )
        for key in keys
    }
