"""데이터 모델 정의."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Assumption:
    key: str
    value: float
    unit: str
    value_type: str  # "실제" | "추정" | "가정"
    source: str
    period: str
    notes: str = ""

    def validate_meta(self) -> list[str]:
        errors = []
        if self.value_type not in ("실제", "추정", "가정"):
            errors.append(f"{self.key}: value_type이 실제/추정/가정 중 하나가 아님 ({self.value_type!r})")
        if not self.source:
            errors.append(f"{self.key}: source가 비어 있음")
        if not self.period:
            errors.append(f"{self.key}: period가 비어 있음")
        return errors


@dataclass
class RewardLevel:
    reward_level_id: str
    label: str
    reward_cost_per_conversion: float
    value_type: str
    source: str
    period: str


@dataclass
class Region:
    region_id: str
    region_name: str
    tourist_share: float
    contacted_customers_per_fm: float
    fixed_operation_cost_per_fm: float
    value_type: str
    source: str
    period: str


@dataclass
class Scenario:
    scenario_id: str
    region_id: str
    fm_count: int
    reward_level_id: str
    label: str


@dataclass
class GroupPnL:
    group: str  # "treatment" | "control"
    contacted_total: float
    contacted_tourist: float
    contacted_domestic: float
    new_customers_tourist: float
    new_customers_domestic: float
    revenue_tourist: float
    revenue_domestic: float
    revenue_total: float
    acquisition_cost: float
    delivery_cost: float
    fixed_cost: float
    cost_excl_initial: float
    profit_excl_initial: float
    initial_cost_applied: float
    profit_incl_initial: float


@dataclass
class ScenarioPnL:
    scenario_id: str
    region_id: str
    reward_level_id: str
    label: str
    treatment: GroupPnL
    control: GroupPnL
    incremental_profit_excl_initial: float
    incremental_profit_incl_initial: float
    assumptions_version: str
    calc_version: str

    def reconcile(self, tolerance: float) -> list[str]:
        errors = []
        for g in (self.treatment, self.control):
            recomputed = g.revenue_total - g.cost_excl_initial
            if abs(recomputed - g.profit_excl_initial) > tolerance:
                errors.append(
                    f"{self.scenario_id}/{g.group}: profit_excl_initial 재계산 불일치 "
                    f"(저장값={g.profit_excl_initial}, 재계산값={recomputed})"
                )
            recomputed_incl = g.profit_excl_initial - g.initial_cost_applied
            if abs(recomputed_incl - g.profit_incl_initial) > tolerance:
                errors.append(
                    f"{self.scenario_id}/{g.group}: profit_incl_initial 재계산 불일치"
                )
            segsum = g.contacted_tourist + g.contacted_domestic
            if abs(segsum - g.contacted_total) > tolerance:
                errors.append(f"{self.scenario_id}/{g.group}: 세그먼트 접촉수 합계 불일치")
        expected_incr_excl = self.treatment.profit_excl_initial - self.control.profit_excl_initial
        if abs(expected_incr_excl - self.incremental_profit_excl_initial) > tolerance:
            errors.append(f"{self.scenario_id}: 증분이익(초기비용 제외) 재계산 불일치")
        expected_incr_incl = self.treatment.profit_incl_initial - self.control.profit_incl_initial
        if abs(expected_incr_incl - self.incremental_profit_incl_initial) > tolerance:
            errors.append(f"{self.scenario_id}: 증분이익(초기비용 포함) 재계산 불일치")
        return errors
