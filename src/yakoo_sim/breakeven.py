"""손익분기 조건 계산 — "무엇이 얼마나 달라져야 판단이 바뀌는가".

일반판촉 대비 추가 손익이 0이 되는 지점(손익분기)을 레버별로 찾는다.
방법은 결정론적 이분법(bisection)이며, 확률분포나 난수를 쓰지 않는다.
손익 계산 자체는 calculator.compute_scenario_pnl 을 그대로 재사용한다.

탐색 범위 안에서 부호가 바뀌지 않으면(= 그 레버만 움직여서는 손익분기에
도달하지 못하면) 값을 만들어내지 않고 None 과 사유를 함께 반환한다.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .calculator import compute_scenario_pnl
from .models import Assumption, Region, RewardLevel, Scenario

# 손익(원) 기준 수렴 허용치. 구간 폭이 아니라 손익 오차로 판정해야
# 레버 단위(비율 0~1 vs 금액 0~100만원)에 상관없이 같은 정확도가 나온다.
DEFAULT_TOLERANCE = 1e-6
DEFAULT_MAX_ITER = 200


@dataclass
class BreakevenResult:
    lever: str                     # 레버 식별자 (assumption key 또는 "reward_cost_per_conversion")
    label: str                     # 화면 표시용 이름
    current_value: float           # 현재 가정값
    breakeven_value: float | None  # 손익분기가 되는 값 (없으면 None)
    gap: float | None              # breakeven - current (없으면 None)
    unavailable_reason: str | None # 손익분기를 찾지 못한 사유
    include_initial: bool          # 초기 제작비 포함 기준인지
    # 손익분기를 못 찾은 경우, 탐색 범위 양 끝에서의 손익 부호.
    # "always_profit"  = 범위 전체에서 이익 (이 값을 아무리 낮춰도 손익분기 아래로 안 감)
    # "always_loss"    = 범위 전체에서 손실 (이 값을 아무리 올려도 손익분기에 못 감)
    endpoints_sign: str | None = None


def _profit(scenario: Scenario, region: Region, reward_level: RewardLevel,
            assumptions: dict[str, Assumption], include_initial: bool) -> float:
    pnl = compute_scenario_pnl(scenario, region, reward_level, assumptions, "breakeven-probe")
    return pnl.incremental_profit_incl_initial if include_initial else pnl.incremental_profit_excl_initial


def _bisect(profit_at, lo: float, hi: float, tolerance: float,
            max_iter: int) -> tuple[float | None, str | None, str | None]:
    """profit_at(x) == 0 이 되는 x 를 [lo, hi] 에서 이분법으로 찾는다.

    반환: (값, 못 찾은 사유, 범위 양 끝 손익 부호)
    수렴 판정은 손익 오차(tolerance, 원) 기준이며, 부동소수점 한계에 도달하면
    더 이상 좁힐 수 없으므로 그 지점의 값을 반환한다.
    """
    f_lo, f_hi = profit_at(lo), profit_at(hi)
    if f_lo == 0:
        return lo, None, None
    if f_hi == 0:
        return hi, None, None
    if (f_lo > 0) == (f_hi > 0):
        sign = "always_profit" if f_lo > 0 else "always_loss"
        return None, (
            f"탐색 범위({lo:g}~{hi:g}) 전체에서 "
            f"{'이익' if f_lo > 0 else '손실'}이라, 이 값만 바꿔서는 손익분기점이 나타나지 않습니다."
        ), sign
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        if mid == lo or mid == hi:  # 더 이상 구간을 좁힐 수 없는 부동소수점 한계
            return mid, None, None
        f_mid = profit_at(mid)
        if abs(f_mid) < tolerance:
            return mid, None, None
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return (lo + hi) / 2, None, None


def solve_breakeven_assumption(
    scenario: Scenario,
    region: Region,
    reward_level: RewardLevel,
    assumptions: dict[str, Assumption],
    key: str,
    label: str,
    lo: float,
    hi: float,
    include_initial: bool = True,
    tolerance: float = DEFAULT_TOLERANCE,
    max_iter: int = DEFAULT_MAX_ITER,
) -> BreakevenResult:
    """가정값 하나(전환율, 재구매율 등)를 움직여 손익분기가 되는 값을 찾는다."""
    if key not in assumptions:
        return BreakevenResult(key, label, float("nan"), None, None,
                                f"가정값 '{key}' 이 입력되지 않아 계산할 수 없습니다.", include_initial, None)

    current = assumptions[key].value

    def profit_at(value: float) -> float:
        probe = deepcopy(assumptions)
        original = probe[key]
        probe[key] = Assumption(
            key=key, value=value, unit=original.unit, value_type=original.value_type,
            source=original.source + " [손익분기 탐색값]", period=original.period,
        )
        return _profit(scenario, region, reward_level, probe, include_initial)

    value, reason, sign = _bisect(profit_at, lo, hi, tolerance, max_iter)
    gap = (value - current) if value is not None else None
    return BreakevenResult(key, label, current, value, gap, reason, include_initial, sign)


def solve_breakeven_reward_cost(
    scenario: Scenario,
    region: Region,
    reward_level: RewardLevel,
    assumptions: dict[str, Assumption],
    lo: float = 0.0,
    hi: float = 1_000_000.0,
    include_initial: bool = True,
    tolerance: float = DEFAULT_TOLERANCE,
    max_iter: int = DEFAULT_MAX_ITER,
) -> BreakevenResult:
    """보상비(전환 1건당 지급액)를 움직여 손익분기가 되는 금액을 찾는다."""
    current = reward_level.reward_cost_per_conversion

    def profit_at(cost: float) -> float:
        probe_reward = RewardLevel(
            reward_level_id=reward_level.reward_level_id, label=reward_level.label,
            reward_cost_per_conversion=cost, value_type=reward_level.value_type,
            source=reward_level.source + " [손익분기 탐색값]", period=reward_level.period,
        )
        return _profit(scenario, region, probe_reward, assumptions, include_initial)

    value, reason, sign = _bisect(profit_at, lo, hi, tolerance, max_iter)
    gap = (value - current) if value is not None else None
    return BreakevenResult("reward_cost_per_conversion", "보상비 (전환 1건당)",
                            current, value, gap, reason, include_initial, sign)
