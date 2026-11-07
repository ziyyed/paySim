#!/usr/bin/env python3
"""Streaming, bounded-memory audit for the public Kaggle PaySim CSV.

The source checksum is computed in fixed-size chunks. CSV rows are parsed one
at a time. Optional exact duplicate detection uses a temporary SQLite index on
disk, not a Python set, so RAM usage stays bounded.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import tempfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

DATASET_URL = "https://www.kaggle.com/datasets/ealaxi/paysim1"
EXPECTED_COLUMNS = [
    "step",
    "type",
    "amount",
    "nameOrig",
    "oldbalanceOrg",
    "newbalanceOrig",
    "nameDest",
    "oldbalanceDest",
    "newbalanceDest",
    "isFraud",
    "isFlaggedFraud",
]
NUMERIC_COLUMNS = [
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
]
KNOWN_TYPES = {"CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"}
EXPECTED_MAX_STEP = 744
HASH_CHUNK_SIZE = 8 * 1024 * 1024
DUPLICATE_BATCH_SIZE = 5000


def sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def parse_decimal(value: str) -> Decimal | None:
    try:
        number = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        return None
    return number if number.is_finite() else None


def flush_digests(connection: sqlite3.Connection, digests: list[bytes]) -> int:
    if not digests:
        return 0
    before = connection.total_changes
    connection.executemany(
        "INSERT OR IGNORE INTO seen (digest) VALUES (?)",
        ((digest,) for digest in digests),
    )
    inserted = connection.total_changes - before
    duplicates = len(digests) - inserted
    digests.clear()
    return duplicates


def audit(path: Path, duplicate_detection: bool = True) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)

    source_sha256, source_size = sha256_and_size(path)
    rejected: Counter[str] = Counter()
    row_count = valid_rows = 0
    min_step: int | None = None
    max_step: int | None = None
    class_by_step: dict[int, Counter[str]] = defaultdict(Counter)
    class_totals: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    flagged_counts: Counter[str] = Counter()
    destination_prefix_counts: Counter[str] = Counter()
    blank_cells: Counter[str] = Counter()
    quality = Counter()
    duplicate_rows = 0
    header: list[str] | None = None
    column_positions: dict[str, int] = {}
    header_matches_expected = False
    column_order_matches_expected = False
    duplicate_batch: list[bytes] = []

    temp_context = tempfile.TemporaryDirectory(prefix="paysim_audit_") if duplicate_detection else None
    connection: sqlite3.Connection | None = None
    try:
        if duplicate_detection:
            assert temp_context is not None
            connection = sqlite3.connect(str(Path(temp_context.name) / "seen.sqlite3"))
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute("PRAGMA cache_size=-16384")
            connection.execute("CREATE TABLE seen (digest BLOB PRIMARY KEY) WITHOUT ROWID")

        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            header = next(reader, None)
            if header is None:
                raise ValueError("CSV is empty; expected a header row.")
            header_matches_expected = (
                len(header) == len(EXPECTED_COLUMNS)
                and set(header) == set(EXPECTED_COLUMNS)
            )
            column_order_matches_expected = header == EXPECTED_COLUMNS
            if not header_matches_expected:
                raise ValueError(
                    "Unexpected CSV schema. "
                    f"Expected exactly these 11 columns: {EXPECTED_COLUMNS!r}; "
                    f"observed: {header!r}"
                )
            column_positions = {name: index for index, name in enumerate(header)}

            for row in reader:
                row_count += 1
                if duplicate_detection:
                    canonical_row = json.dumps(
                        row, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8")
                    duplicate_batch.append(hashlib.sha256(canonical_row).digest())
                    if len(duplicate_batch) >= DUPLICATE_BATCH_SIZE:
                        assert connection is not None
                        duplicate_rows += flush_digests(connection, duplicate_batch)

                if len(row) == len(header):
                    for name, index in column_positions.items():
                        if not row[index].strip():
                            blank_cells[name] += 1

                reason: str | None = None
                if not row:
                    reason = "empty_row"
                elif len(row) != len(header):
                    reason = "wrong_field_count"
                elif row == header:
                    reason = "duplicate_header"
                elif any(not row[column_positions[name]].strip() for name in (
                    "step", "type", "amount", "nameOrig", "nameDest",
                    "isFraud", "isFlaggedFraud",
                )):
                    reason = "missing_required_value"

                step: int | None = None
                amount: Decimal | None = None
                label: str | None = None
                flag: str | None = None

                if reason is None:
                    try:
                        step = int(row[column_positions["step"]].strip())
                    except (ValueError, AttributeError):
                        reason = "invalid_step"
                    else:
                        if step < 1 or step > EXPECTED_MAX_STEP:
                            reason = "step_out_of_documented_range"

                if reason is None:
                    amount = parse_decimal(row[column_positions["amount"]])
                    if amount is None:
                        reason = "invalid_amount"
                    elif amount < 0:
                        reason = "negative_amount"

                if reason is None:
                    bad_balance = False
                    for name in NUMERIC_COLUMNS[1:]:
                        parsed = parse_decimal(row[column_positions[name]])
                        if parsed is None:
                            bad_balance = True
                            break
                        if parsed < 0:
                            quality["negative_balance_values"] += 1
                    if bad_balance:
                        reason = "invalid_balance"

                if reason is None:
                    label = row[column_positions["isFraud"]].strip()
                    if label not in {"0", "1"}:
                        reason = "invalid_isFraud"

                if reason is None:
                    flag = row[column_positions["isFlaggedFraud"]].strip()
                    if flag not in {"0", "1"}:
                        reason = "invalid_isFlaggedFraud"

                if reason is not None:
                    rejected[reason] += 1
                    continue

                assert step is not None and amount is not None
                assert label is not None and flag is not None
                valid_rows += 1
                min_step = step if min_step is None else min(min_step, step)
                max_step = step if max_step is None else max(max_step, step)
                class_name = "fraud" if label == "1" else "normal"
                class_by_step[step][class_name] += 1
                class_totals[class_name] += 1
                type_value = row[column_positions["type"]].strip()
                type_counts[type_value] += 1
                if type_value not in KNOWN_TYPES:
                    quality["unknown_type_rows"] += 1
                flagged_counts[flag] += 1
                if amount == 0:
                    quality["zero_amount_rows"] += 1
                destination = row[column_positions["nameDest"]].strip()
                destination_prefix_counts[
                    "merchant_M" if destination.startswith("M") else "other"
                ] += 1

        if duplicate_detection:
            assert connection is not None
            duplicate_rows += flush_digests(connection, duplicate_batch)
            connection.commit()
        if valid_rows + sum(rejected.values()) != row_count:
            raise AssertionError("Accepted and rejected rows do not reconcile.")
        if sum(class_totals.values()) != valid_rows:
            raise AssertionError("Fraud/normal counts do not reconcile to valid rows.")

        return {
            "audit_schema_version": 1,
            "dataset": {
                "title": "Synthetic Financial Datasets For Fraud Detection (PaySim)",
                "source_url": DATASET_URL,
                "license": "CC BY-SA 4.0",
                "source_file": path.name,
                "source_size_bytes": source_size,
                "source_sha256": source_sha256,
            },
            "schema": {
                "expected_columns": EXPECTED_COLUMNS,
                "observed_columns": header,
                "expected_column_count": len(EXPECTED_COLUMNS),
                "observed_column_count": len(header or []),
                "matches_expected_columns": header_matches_expected,
                "matches_expected_order": column_order_matches_expected,
            },
            "rows": {
                "data_rows": row_count,
                "valid_rows": valid_rows,
                "rejected_rows": sum(rejected.values()),
                "reconciles": valid_rows + sum(rejected.values()) == row_count,
                "rejections_by_reason": dict(sorted(rejected.items())),
            },
            "step_range": {"min": min_step, "max": max_step},
            "class_counts_by_step": {
                str(step): {
                    "normal": counts["normal"],
                    "fraud": counts["fraud"],
                }
                for step, counts in sorted(class_by_step.items())
            },
            "class_totals": {
                "normal": class_totals["normal"],
                "fraud": class_totals["fraud"],
            },
            "quality": {
                "transaction_type_counts": dict(sorted(type_counts.items())),
                "flagged_fraud_counts": {
                    "0": flagged_counts["0"],
                    "1": flagged_counts["1"],
                },
                "destination_prefix_counts": dict(sorted(destination_prefix_counts.items())),
                "blank_cells_by_column": dict(sorted(blank_cells.items())),
                "zero_amount_rows": quality["zero_amount_rows"],
                "negative_balance_values": quality["negative_balance_values"],
                "unknown_type_rows": quality["unknown_type_rows"],
                "exact_duplicate_rows": duplicate_rows if duplicate_detection else None,
                "exact_duplicate_detection": (
                    "disk-backed SQLite over parsed data-row fields"
                    if duplicate_detection
                    else "disabled"
                ),
                "duplicates_removed": 0,
            },
        }
    finally:
        if connection is not None:
            connection.close()
        if temp_context is not None:
            temp_context.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Path to the downloaded PaySim CSV")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write deterministic JSON manifest to this path (also print it)",
    )
    parser.add_argument(
        "--skip-duplicate-check",
        action="store_true",
        help="Skip exact duplicate detection; this still uses bounded RAM.",
    )
    args = parser.parse_args()

    result = audit(args.csv_path, duplicate_detection=not args.skip_duplicate_check)
    output = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())