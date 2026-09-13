#!/usr/bin/env python3
"""가상(더미) 파일럿 실적 예제 데이터를 생성한다.

이 스크립트는 시연/테스트 목적의 합성 데이터를 만들 뿐이며, 실제 고객
데이터가 아니다. yakoo_sim.config.RANDOM_SEED 로 고정된 난수 시드를 사용해
언제 실행해도 동일한 결과가 나오도록 재현성을 보장한다.

산출:
  data/input/pilot/pilot_conversion_2026q2.csv   (관찰기간이 충분히 지난 구(舊) 배치)
  data/input/pilot/pilot_repeat_purchase_2026q2.csv
  data/input/pilot/pilot_conversion_2026q3.csv   (아직 관찰기간이 안 지난 신(新) 배치)
  data/input/pilot/pilot_repeat_purchase_2026q3.csv
"""
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from yakoo_sim.config import RANDOM_SEED  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "input" / "pilot"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REGIONS = ["jeju", "seoul", "busan"]
GROUPS = ["treatment", "control"]

# 합성 데이터 생성에만 쓰이는 "숨겨진 참값" — 실제 사업 수치가 아님을 명시.
# 파일럿 결과가 assumptions.json 의 사전 가정과 다르게 나오도록 일부러 편차를 둠.
TRUE_CONVERSION = {
    ("domestic", "treatment"): 0.19,
    ("tourist", "treatment"): 0.07,
    ("domestic", "control"): 0.095,
    ("tourist", "control"): 0.045,
}
TOURIST_SHARE = {"jeju": 0.55, "seoul": 0.15, "busan": 0.30}
TRUE_REPEAT_RATE = 0.27
TRUE_REPEAT_ORDER_CHOICES = [1, 1, 2, 2, 3]  # 재구매 발생 시 횟수 분포(단순 격자)

CONVERSION_WINDOW_DAYS = 7
REPEAT_WINDOW_DAYS = 90


def gen_batch(rng, batch_label, n_per_region_group, contact_start, contact_span_days):
    conv_rows = []
    repeat_rows = []
    record_seq = 0
    for region in REGIONS:
        for group in GROUPS:
            for _ in range(n_per_region_group):
                record_seq += 1
                customer_id = f"{batch_label}-{region}-{group}-{record_seq:04d}"
                segment = "tourist" if rng.random() < TOURIST_SHARE[region] else "domestic"
                contact_date = contact_start + timedelta(days=rng.randrange(contact_span_days + 1))
                conv_window_end = contact_date + timedelta(days=CONVERSION_WINDOW_DAYS)
                converted = rng.random() < TRUE_CONVERSION[(segment, group)]

                conv_rows.append({
                    "record_id": f"{batch_label}-conv-{record_seq:04d}",
                    "customer_id": customer_id,
                    "region_id": region,
                    "group": group,
                    "segment": segment,
                    "contact_date": contact_date.isoformat(),
                    "converted": "Y" if converted else "N",
                    "conversion_window_end_date": conv_window_end.isoformat(),
                    "source_file": f"pilot_conversion_{batch_label}.csv",
                })

                if converted and segment == "domestic":
                    repeat_window_end = contact_date + timedelta(days=REPEAT_WINDOW_DAYS)
                    has_repeat = rng.random() < TRUE_REPEAT_RATE
                    repeat_orders = rng.choice(TRUE_REPEAT_ORDER_CHOICES) if has_repeat else 0
                    repeat_rows.append({
                        "record_id": f"{batch_label}-rep-{record_seq:04d}",
                        "customer_id": customer_id,
                        "region_id": region,
                        "group": group,
                        "acquisition_date": contact_date.isoformat(),
                        "repeat_orders_count": repeat_orders,
                        "repeat_window_end_date": repeat_window_end.isoformat(),
                        "source_file": f"pilot_repeat_purchase_{batch_label}.csv",
                    })
    return conv_rows, repeat_rows


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows -> {path}")


def main():
    rng = random.Random(RANDOM_SEED)

    # 2026Q2 배치: as_of_date(2026-09-01, 2026-12-01 데모 기준) 로는 전환/재구매
    # 관찰기간이 모두 완료된 "성숙한" 코호트.
    conv_a, rep_a = gen_batch(
        rng, "2026q2",
        n_per_region_group=70,
        contact_start=date(2026, 5, 1),
        contact_span_days=45,  # 2026-05-01 ~ 2026-06-15
    )

    # 2026Q3 배치: as_of_date=2026-09-01 기준으로는 전환은 완료되지만 재구매(90일)는
    # 아직 완료되지 않은 "미성숙" 코호트. as_of_date=2026-12-01 이후에는 성숙됨.
    conv_b, rep_b = gen_batch(
        rng, "2026q3",
        n_per_region_group=25,
        contact_start=date(2026, 8, 15),
        contact_span_days=15,  # 2026-08-15 ~ 2026-08-30
    )

    conv_fields = ["record_id", "customer_id", "region_id", "group", "segment",
                   "contact_date", "converted", "conversion_window_end_date", "source_file"]
    rep_fields = ["record_id", "customer_id", "region_id", "group",
                  "acquisition_date", "repeat_orders_count", "repeat_window_end_date", "source_file"]

    write_csv(OUT_DIR / "pilot_conversion_2026q2.csv", conv_a, conv_fields)
    write_csv(OUT_DIR / "pilot_repeat_purchase_2026q2.csv", rep_a, rep_fields)
    write_csv(OUT_DIR / "pilot_conversion_2026q3.csv", conv_b, conv_fields)
    write_csv(OUT_DIR / "pilot_repeat_purchase_2026q3.csv", rep_b, rep_fields)

    print(f"\nRANDOM_SEED={RANDOM_SEED} (yakoo_sim.config.RANDOM_SEED) 로 생성된 합성 예제 데이터입니다.")
    print("실제 고객/사업 데이터가 아닙니다.")


if __name__ == "__main__":
    main()
