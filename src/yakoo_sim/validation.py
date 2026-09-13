"""검증 로직 — docs/requirements.md 5절 검증 기준 구현.

치명적(critical) 실패가 하나라도 있으면 `expansion_recommendation_allowed=False`
가 되어, report.py는 반드시 "확대 권고 보류" 문구를 출력해야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import RECONCILIATION_TOLERANCE
from .models import Assumption, Region, RewardLevel, Scenario, ScenarioPnL

REQUIRED_ASSUMPTION_KEYS = (
    "conversion_rate_domestic_treatment",
    "conversion_rate_tourist_treatment",
    "conversion_rate_domestic_control",
    "conversion_rate_tourist_control",
    "avg_order_value_domestic",
    "avg_order_value_tourist",
    "repeat_purchase_rate_domestic",
    "avg_repeat_orders_per_repeat_customer_domestic",
    "regular_promo_cost_per_conversion",
    "delivery_cost_per_order_domestic",
    "initial_production_cost_program",
    "conversion_observation_window_days",
    "repeat_purchase_observation_window_days",
)

RATIO_KEYS = (
    "conversion_rate_domestic_treatment", "conversion_rate_tourist_treatment",
    "conversion_rate_domestic_control", "conversion_rate_tourist_control",
    "repeat_purchase_rate_domestic",
)

NONNEGATIVE_KEYS = (
    "avg_order_value_domestic", "avg_order_value_tourist",
    "avg_repeat_orders_per_repeat_customer_domestic",
    "regular_promo_cost_per_conversion", "delivery_cost_per_order_domestic",
    "initial_production_cost_program",
)


@dataclass
class ValidationIssue:
    severity: str  # "critical" | "warning"
    rule: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(i.severity == "critical" for i in self.issues)

    @property
    def expansion_recommendation_allowed(self) -> bool:
        return not self.has_critical

    def to_dict(self) -> dict:
        return {
            "expansion_recommendation_allowed": self.expansion_recommendation_allowed,
            "issues": [i.__dict__ for i in self.issues],
        }


def validate_assumptions(assumptions: dict[str, Assumption]) -> list[ValidationIssue]:
    issues = []
    for key in REQUIRED_ASSUMPTION_KEYS:
        if key not in assumptions:
            issues.append(ValidationIssue("critical", "required_assumption_missing", f"필수 가정값 누락: {key}"))
            continue
        a = assumptions[key]
        for err in a.validate_meta():
            issues.append(ValidationIssue("critical", "assumption_metadata_missing", err))
        if key in RATIO_KEYS and not (0.0 <= a.value <= 1.0):
            issues.append(ValidationIssue("critical", "ratio_out_of_range",
                                           f"{key} 값이 [0,1] 범위를 벗어남: {a.value}"))
        if key in NONNEGATIVE_KEYS and a.value < 0:
            issues.append(ValidationIssue("critical", "negative_value", f"{key} 값이 음수임: {a.value}"))
    return issues


def validate_regions(regions: dict[str, Region]) -> list[ValidationIssue]:
    issues = []
    for r in regions.values():
        if not (0.0 <= r.tourist_share <= 1.0):
            issues.append(ValidationIssue("critical", "ratio_out_of_range",
                                           f"{r.region_id}.tourist_share 범위 오류: {r.tourist_share}"))
        if r.contacted_customers_per_fm < 0 or r.fixed_operation_cost_per_fm < 0:
            issues.append(ValidationIssue("critical", "negative_value", f"{r.region_id} 음수 파라미터 존재"))
        for err in [f"{r.region_id}: {e}" for e in
                    _meta_errors(r.value_type, r.source, r.period, r.region_id)]:
            issues.append(ValidationIssue("critical", "assumption_metadata_missing", err))
    return issues


def _meta_errors(value_type: str, source: str, period: str, label: str) -> list[str]:
    errors = []
    if value_type not in ("실제", "추정", "가정"):
        errors.append(f"value_type이 실제/추정/가정 중 하나가 아님 ({value_type!r})")
    if not source:
        errors.append("source가 비어 있음")
    if not period:
        errors.append("period가 비어 있음")
    return errors


def validate_scenarios_referential(scenarios: list[Scenario], regions: dict[str, Region],
                                    reward_levels: dict[str, RewardLevel]) -> list[ValidationIssue]:
    issues = []
    for sc in scenarios:
        if sc.region_id not in regions:
            issues.append(ValidationIssue("critical", "referential_integrity",
                                           f"{sc.scenario_id}: region_id '{sc.region_id}' 를 regions.csv에서 찾을 수 없음"))
        if sc.reward_level_id not in reward_levels:
            issues.append(ValidationIssue("critical", "referential_integrity",
                                           f"{sc.scenario_id}: reward_level_id '{sc.reward_level_id}' 를 reward_levels.csv에서 찾을 수 없음"))
        if sc.fm_count <= 0:
            issues.append(ValidationIssue("critical", "invalid_scale", f"{sc.scenario_id}: fm_count가 0 이하"))
    return issues


def validate_scenario_results(results: list[ScenarioPnL],
                               tolerance: float = RECONCILIATION_TOLERANCE) -> list[ValidationIssue]:
    issues = []
    for r in results:
        for err in r.reconcile(tolerance):
            issues.append(ValidationIssue("critical", "reconciliation_failed", err))
    return issues


def validate_pilot_sample(rate_estimates: dict, min_sample_size: int) -> list[ValidationIssue]:
    issues = []
    for key, est in rate_estimates.items():
        if est.value is None:
            issues.append(ValidationIssue("warning", "pilot_no_completed_sample",
                                           f"{key}: 관찰기간 완료 표본 0건"))
        elif not est.sufficient_sample:
            issues.append(ValidationIssue("warning", "pilot_sample_too_small",
                                           f"{key}: 표본 부족 (n={est.sample_size} < {min_sample_size})"))
    return issues


def run_full_validation(
    assumptions: dict[str, Assumption],
    regions: dict[str, Region],
    reward_levels: dict[str, RewardLevel],
    scenarios: list[Scenario],
    scenario_results: list[ScenarioPnL],
    pilot_rate_estimates: dict | None = None,
    min_pilot_sample_size: int | None = None,
) -> ValidationReport:
    report = ValidationReport()
    report.issues += validate_assumptions(assumptions)
    report.issues += validate_regions(regions)
    report.issues += validate_scenarios_referential(scenarios, regions, reward_levels)
    report.issues += validate_scenario_results(scenario_results)
    if pilot_rate_estimates is not None:
        report.issues += validate_pilot_sample(pilot_rate_estimates, min_pilot_sample_size)
    return report
