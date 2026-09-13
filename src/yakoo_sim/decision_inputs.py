"""투자 의사결정에 필요한 입력 — 승인 전 근거 체크리스트와 사후 확대 기준.

손익 계산과 달리, 이 모듈은 "지금 이 결정을 내릴 만큼 근거가 갖춰졌는가"를
데이터 파일에서 읽어 그대로 보여주기 위한 것이다. 상태를 코드에 하드코딩하지
않고 CSV에서 읽으므로, 실제 근거가 확보되면 파일만 갱신하면 된다.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

# 근거 확보 상태. '확보'만 실제로 검증된 상태로 인정한다.
STATUS_CONFIRMED = "확보"
STATUS_ORDER = ("확보", "추정", "가정", "미확보", "입력필요")


@dataclass
class ReadinessItem:
    item_id: str
    item: str
    status: str
    value: float | None
    unit: str
    evidence_source: str
    note: str

    @property
    def is_confirmed(self) -> bool:
        return self.status == STATUS_CONFIRMED

    @property
    def needs_input(self) -> bool:
        return self.status == "입력필요"


@dataclass
class ExpansionCriterion:
    criterion_id: str
    criterion: str
    definition: str
    threshold_value: float
    threshold_unit: str
    direction: str      # "이상" | "이하"
    measurement: str    # 측정 방법 식별자 또는 "미측정"
    note: str

    @property
    def is_measurable(self) -> bool:
        return self.measurement != "미측정"


def _parse_float(raw: str) -> float | None:
    raw = (raw or "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def load_decision_readiness(path: str | Path) -> list[ReadinessItem]:
    items = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            items.append(ReadinessItem(
                item_id=row["item_id"], item=row["item"], status=row["status"],
                value=_parse_float(row.get("value", "")), unit=row.get("unit", ""),
                evidence_source=row.get("evidence_source", ""), note=row.get("note", ""),
            ))
    return items


def load_expansion_criteria(path: str | Path) -> list[ExpansionCriterion]:
    criteria = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            criteria.append(ExpansionCriterion(
                criterion_id=row["criterion_id"], criterion=row["criterion"],
                definition=row["definition"],
                threshold_value=float(row["threshold_value"]),
                threshold_unit=row.get("threshold_unit", ""),
                direction=row["direction"], measurement=row.get("measurement", "미측정"),
                note=row.get("note", ""),
            ))
    return criteria


def readiness_summary(items: list[ReadinessItem]) -> dict:
    """승인 판단에 쓸 요약. 모든 항목이 '확보'일 때만 투자 추천을 확정할 수 있다."""
    missing = [i for i in items if not i.is_confirmed]
    return {
        "total": len(items),
        "confirmed": len(items) - len(missing),
        "missing": missing,
        "recommendation_allowed": len(missing) == 0,
    }


def get_readiness_value(items: list[ReadinessItem], item_id: str) -> float | None:
    """확보/입력된 수치가 있는 항목의 값을 가져온다 (없으면 None)."""
    for item in items:
        if item.item_id == item_id:
            return item.value
    return None


def evaluate_expansion_criterion(criterion: ExpansionCriterion, measured_value: float | None) -> dict:
    """사전 기준과 실적을 비교한다. 측정값이 없으면 판정하지 않는다."""
    if measured_value is None:
        return {"criterion": criterion, "measured_value": None, "judgement": "미측정"}
    if criterion.direction == "이상":
        met = measured_value >= criterion.threshold_value
    elif criterion.direction == "이하":
        met = measured_value <= criterion.threshold_value
    else:
        return {"criterion": criterion, "measured_value": measured_value, "judgement": "기준정의오류"}
    return {"criterion": criterion, "measured_value": measured_value,
            "judgement": "충족" if met else "미달"}


def pilot_conversion_gap_pp(conversion_rates: dict) -> float | None:
    """파일럿 실적에서 '일반 판촉 대비 추가 구매'(%p)를 구한다.

    pilot_update.compute_conversion_rates 결과를 그대로 받아, 관찰기간이 완료된
    표본으로 산출된 실험군·비교군 국내 첫구매율의 차이를 %p로 돌려준다.
    둘 중 하나라도 표본이 없으면 None (측정 불가).
    """
    treatment = conversion_rates.get("conversion_rate_domestic_treatment")
    control = conversion_rates.get("conversion_rate_domestic_control")
    if treatment is None or control is None:
        return None
    if treatment.value is None or control.value is None:
        return None
    return (treatment.value - control.value) * 100
