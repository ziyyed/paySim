#!/usr/bin/env python3
"""Check the toy fixture against its hand-calculated Week 1 / MR1 reference."""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_paysim import audit

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "toy_paysim.csv"
EXPECTED = ROOT / "fixtures" / "toy_expected.json"


def normalized(value: Decimal) -> str:
    return format(value.normalize(), "f")


def main() -> int:
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    manifest = audit(FIXTURE, duplicate_detection=True)
    for key in (
        "valid_rows", "rejected_rows", "rejections_by_reason",
    ):
        actual_key = "rejections_by_reason" if key == "rejections_by_reason" else key
        actual = manifest["rows"][actual_key] if key != "rejections_by_reason" else manifest["rows"]["rejections_by_reason"]
        assert actual == expected[key], f"{key}: expected {expected[key]!r}, got {actual!r}"
    assert manifest["rows"]["data_rows"] == expected["fixture_data_rows"]
    assert manifest["rows"]["reconciles"] is True
    assert manifest["step_range"] == expected["step_range"]
    assert manifest["class_totals"] == expected["class_totals"]
    assert manifest["class_counts_by_step"] == expected["class_counts_by_step"]
    assert manifest["quality"]["exact_duplicate_rows"] == 0

    with FIXTURE.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        header = next(reader)
        positions = {name: index for index, name in enumerate(header)}
        aggregates: dict[tuple[str, int], dict] = {}
        for row in reader:
            if len(row) != len(header) or row == header:
                continue
            try:
                step = int(row[positions["step"]])
                amount = Decimal(row[positions["amount"]])
                label = row[positions["isFraud"]]
                flag = row[positions["isFlaggedFraud"]]
                balances = [
                    Decimal(row[positions[name]])
                    for name in ("oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest")
                ]
            except Exception:
                continue
            if not (1 <= step <= 744 and amount.is_finite() and amount >= 0):
                continue
            if any(not value.is_finite() for value in balances) or label not in {"0", "1"} or flag not in {"0", "1"}:
                continue
            key = (row[positions["nameOrig"]], step)
            item = aggregates.setdefault(
                key,
                {"count": 0, "sum": Decimal(0), "max": Decimal(0), "types": Counter()},
            )
            item["count"] += 1
            item["sum"] += amount
            item["max"] = max(item["max"], amount)
            item["types"][row[positions["type"]]] += 1

    actual_aggregates = {
        f"{name}|{step}": {
            "count": item["count"],
            "sum": normalized(item["sum"]),
            "max": normalized(item["max"]),
            "types": dict(sorted(item["types"].items())),
        }
        for (name, step), item in sorted(aggregates.items())
    }
    reference = expected["mr1_reference"]
    assert len(actual_aggregates) == reference["aggregate_count"]
    assert actual_aggregates == reference["aggregates"]
    total = sum((item["sum"] for item in aggregates.values()), Decimal(0))
    maximum = max(item["max"] for item in aggregates.values())
    assert normalized(total) == reference["valid_amount_sum"]
    assert normalized(maximum) == reference["maximum_amount"]
    print("PASS: toy row totals, rejects, class-by-step counts, and all 11 MR1 aggregates match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())