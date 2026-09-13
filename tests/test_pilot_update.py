import csv

from yakoo_sim.models import Assumption
from yakoo_sim.pilot_update import (
    apply_rate_updates,
    compute_conversion_rates,
    compute_repeat_purchase_rates,
    ingest_conversion_file,
)

CONV_FIELDS = ["record_id", "customer_id", "region_id", "group", "segment",
               "contact_date", "converted", "conversion_window_end_date", "source_file"]


def write_conversion_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CONV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def make_conv_row(cid, group, segment, converted, contact_date="2026-01-01", window_end="2026-01-08"):
    return {
        "record_id": f"rec-{cid}", "customer_id": cid, "region_id": "r1", "group": group,
        "segment": segment, "contact_date": contact_date, "converted": converted,
        "conversion_window_end_date": window_end, "source_file": "test.csv",
    }


def test_reingesting_identical_file_does_not_change_counts(tmp_path):
    rows = [make_conv_row(f"c{i}", "treatment", "domestic", "Y" if i % 2 == 0 else "N") for i in range(40)]
    csv_path = tmp_path / "conv.csv"
    write_conversion_csv(csv_path, rows)

    from yakoo_sim.pilot_update import _empty_ledger
    ledger = _empty_ledger()

    r1 = ingest_conversion_file(csv_path, ledger)
    assert r1.rows_new == 40
    assert r1.rows_updated == 0

    rates_after_first = compute_conversion_rates(ledger, "2026-02-01", min_sample_size=1)

    # 동일 파일을 다시 넣는다
    r2 = ingest_conversion_file(csv_path, ledger)
    assert r2.rows_new == 0
    assert r2.rows_updated == 0
    assert r2.rows_unchanged == 40
    assert r2.file_previously_ingested_identical is True

    rates_after_second = compute_conversion_rates(ledger, "2026-02-01", min_sample_size=1)
    key = "conversion_rate_domestic_treatment"
    assert rates_after_first[key].sample_size == rates_after_second[key].sample_size == 40
    assert rates_after_first[key].value == rates_after_second[key].value


def test_incomplete_observation_window_excluded():
    from yakoo_sim.pilot_update import _empty_ledger
    ledger = _empty_ledger()
    ledger["conversion_records"] = {
        "mature1": {
            "region_id": "r1", "group": "treatment", "segment": "domestic",
            "contact_date": "2026-01-01", "converted": True,
            "conversion_window_end_date": "2026-01-08", "source_file": "x", "ingested_at": "t",
        },
        "immature1": {
            "region_id": "r1", "group": "treatment", "segment": "domestic",
            "contact_date": "2026-08-25", "converted": True,
            "conversion_window_end_date": "2026-09-01", "source_file": "x", "ingested_at": "t",
        },
    }
    rates = compute_conversion_rates(ledger, as_of_date="2026-08-30", min_sample_size=1)
    key = "conversion_rate_domestic_treatment"
    # immature1의 window_end(2026-09-01)가 as_of(2026-08-30)보다 뒤이므로 제외되어야 함
    assert rates[key].sample_size == 1
    assert rates[key].value == 1.0


def test_repeat_purchase_rate_excludes_immature_and_computes_correctly():
    from yakoo_sim.pilot_update import _empty_ledger
    ledger = _empty_ledger()
    ledger["repeat_records"] = {
        "a": {"region_id": "r1", "group": "treatment", "acquisition_date": "2026-01-01",
              "repeat_orders_count": 2, "repeat_window_end_date": "2026-04-01",
              "source_file": "x", "ingested_at": "t"},
        "b": {"region_id": "r1", "group": "treatment", "acquisition_date": "2026-01-01",
              "repeat_orders_count": 0, "repeat_window_end_date": "2026-04-01",
              "source_file": "x", "ingested_at": "t"},
        "c_immature": {"region_id": "r1", "group": "treatment", "acquisition_date": "2026-08-01",
                       "repeat_orders_count": 5, "repeat_window_end_date": "2026-11-01",
                       "source_file": "x", "ingested_at": "t"},
    }
    rates = compute_repeat_purchase_rates(ledger, as_of_date="2026-09-01", min_sample_size=1)
    assert rates["repeat_purchase_rate_domestic"].sample_size == 2
    assert rates["repeat_purchase_rate_domestic"].value == 0.5
    assert rates["avg_repeat_orders_per_repeat_customer_domestic"].value == 2.0


def test_apply_rate_updates_keeps_old_value_when_sample_too_small():
    base = {
        "conversion_rate_domestic_treatment": Assumption(
            key="conversion_rate_domestic_treatment", value=0.15, unit="ratio",
            value_type="가정", source="old", period="2026-08"),
    }
    from yakoo_sim.pilot_update import RateEstimate
    estimates = {
        "conversion_rate_domestic_treatment": RateEstimate(
            key="conversion_rate_domestic_treatment", value=0.30, sample_size=3, numerator=1,
            as_of_date="2026-09-01", sufficient_sample=False,
        )
    }
    updated, applied, warnings = apply_rate_updates(base, estimates, "2026-09-01")
    assert updated["conversion_rate_domestic_treatment"].value == 0.15
    assert applied == []
    assert any("표본 부족" in w for w in warnings)


def test_apply_rate_updates_overwrites_when_sample_sufficient():
    base = {
        "conversion_rate_domestic_treatment": Assumption(
            key="conversion_rate_domestic_treatment", value=0.15, unit="ratio",
            value_type="가정", source="old", period="2026-08"),
    }
    from yakoo_sim.pilot_update import RateEstimate
    estimates = {
        "conversion_rate_domestic_treatment": RateEstimate(
            key="conversion_rate_domestic_treatment", value=0.30, sample_size=100, numerator=30,
            as_of_date="2026-09-01", sufficient_sample=True,
        )
    }
    updated, applied, warnings = apply_rate_updates(base, estimates, "2026-09-01")
    assert updated["conversion_rate_domestic_treatment"].value == 0.30
    assert updated["conversion_rate_domestic_treatment"].value_type == "실제"
    assert len(applied) == 1
