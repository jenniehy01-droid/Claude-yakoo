"""파일럿 실적 반영: 중복 방지 적재(ledger) + 관찰기간 완료 고객 기준 전환율/재구매율 갱신.

핵심 설계:
  - 원자료는 `customer_id` 를 기준으로 ledger에 upsert 된다. 같은 파일을
    몇 번을 다시 넣어도, 같은 고객 레코드는 "최신값으로 덮어쓰기"만 될 뿐
    합산되지 않으므로 실적이 중복 반영되지 않는다.
  - 비율(전환율/재구매율) 계산 시점(as_of_date) 기준으로
    `*_window_end_date <= as_of_date` 인 레코드만 사용한다. 즉 관찰 기간이
    아직 끝나지 않은 고객은 갱신에 포함하지 않는다.
  - ledger는 JSON 파일로 영속화되어, 이후 as_of_date가 지나 관찰기간이
    성숙되면 새 파일 없이도 같은 ledger에서 재계산이 가능하다(중복 파일
    투입 불필요).
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .config import MIN_PILOT_SAMPLE_SIZE
from .io_loader import sha256_of_file
from .models import Assumption

SEGMENTS = ("tourist", "domestic")
GROUPS = ("treatment", "control")


def _empty_ledger() -> dict:
    return {"conversion_records": {}, "repeat_records": {}, "ingested_files": {}}


def load_ledger(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        return _empty_ledger()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_ledger(ledger: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2, sort_keys=True)


@dataclass
class IngestResult:
    file_path: str
    file_type: str  # "conversion" | "repeat"
    rows_in_file: int
    rows_new: int
    rows_updated: int
    rows_unchanged: int
    file_previously_ingested_identical: bool


def _register_file(ledger: dict, path: Path, now_iso: str) -> tuple[str, bool]:
    digest = sha256_of_file(path)
    key = str(path)
    prev = ledger["ingested_files"].get(key)
    identical = prev is not None and prev.get("sha256") == digest
    ledger["ingested_files"][key] = {
        "sha256": digest,
        "last_ingested_at": now_iso,
        "first_ingested_at": prev["first_ingested_at"] if prev else now_iso,
    }
    return digest, identical


def ingest_conversion_file(path: str | Path, ledger: dict) -> IngestResult:
    path = Path(path)
    now_iso = datetime.utcnow().isoformat() + "Z"
    _, identical = _register_file(ledger, path, now_iso)

    rows_new = rows_updated = rows_unchanged = 0
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        cid = row["customer_id"]
        record = {
            "region_id": row["region_id"],
            "group": row["group"],
            "segment": row["segment"],
            "contact_date": row["contact_date"],
            "converted": row["converted"].strip().upper() == "Y",
            "conversion_window_end_date": row["conversion_window_end_date"],
            "source_file": row.get("source_file", path.name),
            "ingested_at": now_iso,
        }
        existing = ledger["conversion_records"].get(cid)
        if existing is None:
            rows_new += 1
        elif {k: v for k, v in existing.items() if k != "ingested_at"} == \
                {k: v for k, v in record.items() if k != "ingested_at"}:
            rows_unchanged += 1
            continue  # 값이 동일하면 ingested_at 도 갱신하지 않아 재현성을 유지
        else:
            rows_updated += 1
        ledger["conversion_records"][cid] = record

    return IngestResult(str(path), "conversion", len(rows), rows_new, rows_updated, rows_unchanged, identical)


def ingest_repeat_file(path: str | Path, ledger: dict) -> IngestResult:
    path = Path(path)
    now_iso = datetime.utcnow().isoformat() + "Z"
    _, identical = _register_file(ledger, path, now_iso)

    rows_new = rows_updated = rows_unchanged = 0
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        cid = row["customer_id"]
        record = {
            "region_id": row["region_id"],
            "group": row["group"],
            "acquisition_date": row["acquisition_date"],
            "repeat_orders_count": int(row["repeat_orders_count"]),
            "repeat_window_end_date": row["repeat_window_end_date"],
            "source_file": row.get("source_file", path.name),
            "ingested_at": now_iso,
        }
        existing = ledger["repeat_records"].get(cid)
        if existing is None:
            rows_new += 1
        elif {k: v for k, v in existing.items() if k != "ingested_at"} == \
                {k: v for k, v in record.items() if k != "ingested_at"}:
            rows_unchanged += 1
            continue
        else:
            rows_updated += 1
        ledger["repeat_records"][cid] = record

    return IngestResult(str(path), "repeat", len(rows), rows_new, rows_updated, rows_unchanged, identical)


@dataclass
class RateEstimate:
    key: str
    value: float | None
    sample_size: int
    numerator: int
    as_of_date: str
    sufficient_sample: bool


def compute_conversion_rates(ledger: dict, as_of_date: str, min_sample_size: int = MIN_PILOT_SAMPLE_SIZE
                              ) -> dict[str, RateEstimate]:
    as_of = date.fromisoformat(as_of_date)
    buckets: dict[tuple[str, str], list[bool]] = {(s, g): [] for s in SEGMENTS for g in GROUPS}

    for rec in ledger["conversion_records"].values():
        window_end = date.fromisoformat(rec["conversion_window_end_date"])
        if window_end > as_of:
            continue  # 관찰 기간 미완료 -> 제외
        key = (rec["segment"], rec["group"])
        if key in buckets:
            buckets[key].append(bool(rec["converted"]))

    out = {}
    for (segment, group), values in buckets.items():
        n = len(values)
        conv = sum(1 for v in values if v)
        rate = (conv / n) if n > 0 else None
        assumption_key = f"conversion_rate_{segment}_{group}"
        out[assumption_key] = RateEstimate(
            key=assumption_key, value=rate, sample_size=n, numerator=conv,
            as_of_date=as_of_date, sufficient_sample=n >= min_sample_size,
        )
    return out


def compute_repeat_purchase_rates(ledger: dict, as_of_date: str, min_sample_size: int = MIN_PILOT_SAMPLE_SIZE
                                   ) -> dict[str, RateEstimate]:
    as_of = date.fromisoformat(as_of_date)
    completed = []
    for rec in ledger["repeat_records"].values():
        window_end = date.fromisoformat(rec["repeat_window_end_date"])
        if window_end > as_of:
            continue
        completed.append(rec)

    n = len(completed)
    repeaters = [r for r in completed if r["repeat_orders_count"] >= 1]
    repeat_rate = (len(repeaters) / n) if n > 0 else None
    avg_orders = (sum(r["repeat_orders_count"] for r in repeaters) / len(repeaters)) if repeaters else None

    return {
        "repeat_purchase_rate_domestic": RateEstimate(
            key="repeat_purchase_rate_domestic", value=repeat_rate, sample_size=n,
            numerator=len(repeaters), as_of_date=as_of_date, sufficient_sample=n >= min_sample_size,
        ),
        "avg_repeat_orders_per_repeat_customer_domestic": RateEstimate(
            key="avg_repeat_orders_per_repeat_customer_domestic", value=avg_orders, sample_size=len(repeaters),
            numerator=len(repeaters), as_of_date=as_of_date, sufficient_sample=len(repeaters) >= min_sample_size,
        ),
    }


def apply_rate_updates(
    base_assumptions: dict[str, Assumption],
    rate_estimates: dict[str, RateEstimate],
    as_of_date: str,
) -> tuple[dict[str, Assumption], list[dict], list[str]]:
    """표본이 충분한 항목만 '실제' 값으로 교체한다. 표본 부족 항목은 기존 가정을 유지하고 경고를 남긴다."""
    updated = dict(base_assumptions)
    applied = []
    warnings = []

    for key, est in rate_estimates.items():
        if est.value is None:
            warnings.append(f"{key}: 관찰기간 완료 표본이 0건이라 갱신하지 않음 (기존 가정 유지)")
            continue
        if not est.sufficient_sample:
            warnings.append(
                f"{key}: 표본 부족(n={est.sample_size} < {MIN_PILOT_SAMPLE_SIZE}) — 기존 가정 유지, 참고용으로만 기록"
            )
            continue
        old = base_assumptions.get(key)
        new_assumption = Assumption(
            key=key, value=est.value, unit=old.unit if old else "ratio",
            value_type="실제",
            source=f"파일럿 실적 집계 (n={est.sample_size}, 전환/성공 {est.numerator}건)",
            period=f"~{as_of_date} 기준 관찰기간 완료 고객",
        )
        updated[key] = new_assumption
        applied.append({
            "key": key,
            "old_value": old.value if old else None,
            "old_value_type": old.value_type if old else None,
            "new_value": est.value,
            "sample_size": est.sample_size,
            "as_of_date": as_of_date,
        })

    return updated, applied, warnings
