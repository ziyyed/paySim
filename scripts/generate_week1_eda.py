#!/usr/bin/env python3
"""Generate reproducible Week 1 PaySim charts and a leakage-safe sample.

The full CSV remains local. This script writes figures and summary metadata to
the repository, plus a small two-step sample with predictors and labels split
into separate files.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from audit_paysim import EXPECTED_COLUMNS, sha256_and_size

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEATURE_FIELDS = ["step", "type", "amount", "nameOrig", "nameDest"]
LABEL_FIELD = "isFraud"
EXCLUDED_FEATURE_FIELDS = [
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
    "isFlaggedFraud",
]
TYPE_ORDER = ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]
SAMPLE_MIN_STEP = 1
SAMPLE_MAX_STEP = 2
RESERVOIR_PER_TYPE = 10_000
RESERVOIR_SEED = 42


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def verify_audit(source: Path, manifest: dict[str, Any]) -> tuple[str, int]:
    source_sha256, source_size = sha256_and_size(source)
    dataset = manifest["dataset"]
    if source_sha256 != dataset["source_sha256"]:
        raise ValueError("CSV SHA-256 does not match the checked-in audit manifest.")
    if source_size != dataset["source_size_bytes"]:
        raise ValueError("CSV byte size does not match the checked-in audit manifest.")
    if manifest["schema"]["observed_columns"] != EXPECTED_COLUMNS:
        raise ValueError("Audit manifest does not contain the expected 11-column schema.")
    if manifest["rows"]["rejected_rows"] != 0:
        raise ValueError("This EDA script expects the audited source with zero rejected rows.")
    return source_sha256, source_size


def sample_reservoirs(source: Path, manifest: dict[str, Any], output_root: Path) -> dict[str, Any]:
    sample_dir = output_root / "data" / "samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    features_path = sample_dir / "steps_001_002_features.csv"
    labels_path = sample_dir / "steps_001_002_labels.csv"

    feature_fields = ["source_row_id", *FEATURE_FIELDS]
    label_fields = ["source_row_id", LABEL_FIELD]
    by_step: dict[int, Counter[str]] = defaultdict(Counter)
    class_totals: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    sample_rows = sample_fraud = 0
    total_rows = 0
    rejected_rows = 0
    reservoir_seen: Counter[str] = Counter()
    reservoir: dict[str, list[float]] = {name: [] for name in TYPE_ORDER}
    rng = random.Random(RESERVOIR_SEED)

    with source.open("r", encoding="utf-8-sig", newline="") as stream, \
            features_path.open("w", encoding="utf-8", newline="") as features_file, \
            labels_path.open("w", encoding="utf-8", newline="") as labels_file:
        reader = csv.reader(stream, strict=True)
        header = next(reader, None)
        if header != EXPECTED_COLUMNS:
            raise ValueError(f"Unexpected header: {header!r}")
        features_writer = csv.DictWriter(
            features_file, fieldnames=feature_fields, lineterminator="\n"
        )
        labels_writer = csv.DictWriter(
            labels_file, fieldnames=label_fields, lineterminator="\n"
        )
        features_writer.writeheader()
        labels_writer.writeheader()

        for row_number, row in enumerate(reader, start=1):
            total_rows += 1
            if len(row) != len(EXPECTED_COLUMNS):
                rejected_rows += 1
                continue
            try:
                step = int(row[0])
                amount = float(row[2])
                fraud_label = int(row[9])
                transaction_type = row[1]
            except (ValueError, IndexError):
                rejected_rows += 1
                continue
            if (
                not math.isfinite(amount)
                or amount < 0
                or fraud_label not in (0, 1)
                or step < 1
                or transaction_type not in TYPE_ORDER
            ):
                rejected_rows += 1
                continue

            class_name = "fraud" if fraud_label else "normal"
            by_step[step][class_name] += 1
            class_totals[class_name] += 1
            type_counts[transaction_type] += 1

            reservoir_seen[transaction_type] += 1
            current = reservoir[transaction_type]
            if len(current) < RESERVOIR_PER_TYPE:
                current.append(amount)
            else:
                position = rng.randrange(reservoir_seen[transaction_type])
                if position < RESERVOIR_PER_TYPE:
                    current[position] = amount

            if SAMPLE_MIN_STEP <= step <= SAMPLE_MAX_STEP:
                sample_rows += 1
                sample_fraud += fraud_label
                source_row_id = f"paysim-row-{row_number:08d}"
                features_writer.writerow(
                    {
                        "source_row_id": source_row_id,
                        "step": row[0],
                        "type": row[1],
                        "amount": row[2],
                        "nameOrig": row[3],
                        "nameDest": row[6],
                    }
                )
                labels_writer.writerow(
                    {"source_row_id": source_row_id, LABEL_FIELD: row[9]}
                )

    if rejected_rows:
        raise ValueError(f"Unexpectedly found {rejected_rows} rejected rows after audit.")
    if total_rows != manifest["rows"]["data_rows"]:
        raise ValueError("EDA row count differs from the official audit manifest.")
    if dict(sorted(class_totals.items())) != manifest["class_totals"]:
        raise ValueError("EDA class totals differ from the official audit manifest.")
    normalized_by_step = {
        str(step): {"normal": counts["normal"], "fraud": counts["fraud"]}
        for step, counts in sorted(by_step.items())
    }
    if normalized_by_step != manifest["class_counts_by_step"]:
        raise ValueError("EDA fraud-by-step counts differ from the audit manifest.")

    expected_sample = sum(
        manifest["class_counts_by_step"].get(str(step), {}).get("normal", 0)
        + manifest["class_counts_by_step"].get(str(step), {}).get("fraud", 0)
        for step in range(SAMPLE_MIN_STEP, SAMPLE_MAX_STEP + 1)
    )
    if sample_rows != expected_sample:
        raise ValueError("The two-step sample row count differs from the source manifest.")

    return {
        "total_rows_scanned": total_rows,
        "rejected_rows": rejected_rows,
        "class_totals": dict(sorted(class_totals.items())),
        "transaction_type_counts": dict(sorted(type_counts.items())),
        "class_counts_by_step": normalized_by_step,
        "amount_reservoir": {
            "seed": RESERVOIR_SEED,
            "maximum_per_type": RESERVOIR_PER_TYPE,
            "observed_per_type": {
                name: len(reservoir[name]) for name in TYPE_ORDER
            },
            "amounts_by_type": reservoir,
        },
        "sample": {
            "rule": "all source rows with 1 <= step <= 2, in source order",
            "step_min": SAMPLE_MIN_STEP,
            "step_max": SAMPLE_MAX_STEP,
            "rows_before": sample_rows,
            "rows_after_features": sample_rows,
            "rows_after_labels": sample_rows,
            "fraud_rows": sample_fraud,
            "normal_rows": sample_rows - sample_fraud,
            "feature_file": features_path.relative_to(output_root).as_posix(),
            "feature_file_sha256": sha256_file(features_path),
            "feature_file_size_bytes": features_path.stat().st_size,
            "label_file": labels_path.relative_to(output_root).as_posix(),
            "label_file_sha256": sha256_file(labels_path),
            "label_file_size_bytes": labels_path.stat().st_size,
            "feature_file_columns": feature_fields,
            "predictor_columns": FEATURE_FIELDS,
            "label_file_columns": label_fields,
            "excluded_from_predictors": EXCLUDED_FEATURE_FIELDS,
            "row_count_preserved": True,
        },
    }


def make_figures(
    manifest: dict[str, Any],
    scan: dict[str, Any],
    figure_dir: Path,
    output_root: Path,
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    figure_dir.mkdir(parents=True, exist_ok=True)
    figures: list[str] = []
    class_totals = manifest["class_totals"]
    total = class_totals["normal"] + class_totals["fraud"]
    prevalence = 100.0 * class_totals["fraud"] / total

    # Exact class totals from the full-source audit.
    fig, ax = plt.subplots(figsize=(8.2, 5.0), constrained_layout=True)
    labels = ["Normales", "Fraudes"]
    values = [class_totals["normal"], class_totals["fraud"]]
    colors = ["#2563EB", "#E45756"]
    bars = ax.bar(labels, values, color=colors, width=0.56)
    ax.set_yscale("log")
    ax.set_ylabel("Nombre de transactions (échelle logarithmique)")
    ax.set_title(f"Déséquilibre des classes — {total:,} transactions".replace(",", " "))
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, values):
        ax.annotate(
            f"{value:,}".replace(",", " "),
            (bar.get_x() + bar.get_width() / 2, value),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=10,
        )
    ax.text(
        0.98,
        0.94,
        f"Fraudes : {prevalence:.4f} %",
        transform=ax.transAxes,
        ha="right",
        va="top",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9},
    )
    path = figure_dir / "class-imbalance.png"
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)
    figures.append(path.relative_to(output_root).as_posix())

    # Exact class counts per simulated hour from the official audit.
    steps = sorted(int(step) for step in manifest["class_counts_by_step"])
    normal = [manifest["class_counts_by_step"][str(step)]["normal"] for step in steps]
    fraud = [manifest["class_counts_by_step"][str(step)]["fraud"] for step in steps]
    fig, axes = plt.subplots(2, 1, figsize=(11.0, 7.0), sharex=True, constrained_layout=True)
    axes[0].plot(steps, normal, color="#2563EB", linewidth=1.25)
    axes[0].set_ylabel("Transactions normales")
    axes[0].set_title("Volume horaire par classe — PaySim")
    axes[0].grid(alpha=0.22)
    axes[1].plot(steps, fraud, color="#E45756", linewidth=1.25)
    axes[1].set_ylabel("Transactions frauduleuses")
    axes[1].set_xlabel("Step (heure simulée)")
    axes[1].grid(alpha=0.22)
    fig.suptitle("Distribution des transactions par step (1–743)", fontsize=14)
    path = figure_dir / "fraud-by-step.png"
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)
    figures.append(path.relative_to(output_root).as_posix())

    # Deterministic reservoir sample; amounts are shown on a log1p scale.
    amount_samples = scan["amount_reservoir"]["amounts_by_type"]
    plot_types = [name for name in TYPE_ORDER if amount_samples[name]]
    plot_values = [
        np.log10(1.0 + np.asarray(amount_samples[name], dtype=float))
        for name in plot_types
    ]
    fig, ax = plt.subplots(figsize=(10.2, 5.5), constrained_layout=True)
    boxes = ax.boxplot(
        plot_values,
        tick_labels=plot_types,
        showfliers=False,
        patch_artist=True,
        medianprops={"color": "#111827", "linewidth": 1.4},
    )
    palette = ["#60A5FA", "#34D399", "#FBBF24", "#A78BFA", "#F87171"]
    for box, color in zip(boxes["boxes"], palette):
        box.set_facecolor(color)
        box.set_alpha(0.78)
    ax.set_ylabel("log10(1 + montant)")
    ax.set_xlabel("Type de transaction")
    ax.set_title("Dispersion des montants par type — échantillon reservoir déterministe")
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    ax.text(
        0.99,
        0.02,
        f"Graine {RESERVOIR_SEED} · max. {RESERVOIR_PER_TYPE:,} lignes/type".replace(",", " "),
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#475569",
    )
    path = figure_dir / "amount-dispersion-by-type.png"
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)
    figures.append(path.relative_to(output_root).as_posix())

    # Before/after transformation proof for the reproducible pilot sample.
    sample = scan["sample"]
    fig, ax = plt.subplots(figsize=(13.0, 5.7), constrained_layout=True)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 5.7)
    ax.axis("off")
    boxes = [
        {
            "x": 0.3,
            "title": "AVANT — source PaySim",
            "body": "CSV officiel\n6 362 620 lignes × 11 colonnes\nStep, type, amount, identifiants,\n4 soldes, isFraud, isFlaggedFraud",
            "color": "#DBEAFE",
        },
        {
            "x": 4.55,
            "title": "APRÈS — contrôle qualité",
            "body": "6 362 620 lignes conservées\n0 rejet · 0 doublon exact\nEn-tête et ordre des 11 colonnes conformes\nAucune correction silencieuse",
            "color": "#DCFCE7",
        },
        {
            "x": 8.8,
            "title": "APRÈS — préparation du sample",
            "body": f"Steps 1–2 : {sample['rows_before']:,} lignes\n5 prédicteurs autorisés\nLabel isFraud dans un fichier séparé\n{sample['fraud_rows']} fraudes · {sample['normal_rows']} normales",
            "color": "#FEF3C7",
        },
    ]
    for item in boxes:
        patch = FancyBboxPatch(
            (item["x"], 1.1),
            3.85,
            3.45,
            boxstyle="round,pad=0.12,rounding_size=0.14",
            linewidth=1.2,
            edgecolor="#64748B",
            facecolor=item["color"],
        )
        ax.add_patch(patch)
        ax.text(item["x"] + 1.925, 4.05, item["title"], ha="center", va="center", weight="bold", fontsize=10)
        ax.text(item["x"] + 1.925, 2.75, item["body"], ha="center", va="center", fontsize=9, linespacing=1.5)
    for start, end in [(4.18, 4.48), (8.43, 8.73)]:
        ax.add_patch(
            FancyArrowPatch(
                (start, 2.82),
                (end, 2.82),
                arrowstyle="-|>",
                mutation_scale=16,
                linewidth=1.5,
                color="#334155",
            )
        )
    ax.text(
        6.5,
        0.55,
        "Variables écartées des prédicteurs : 4 soldes post-transaction + isFlaggedFraud. Aucune ligne du sample n’est supprimée.",
        ha="center",
        va="center",
        fontsize=9,
        color="#334155",
    )
    path = figure_dir / "before-after-preparation.png"
    fig.savefig(path, dpi=180, facecolor="white")
    plt.close(fig)
    figures.append(path.relative_to(output_root).as_posix())
    return figures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Path to the official downloaded PaySim CSV")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "results" / "paysim-audit-manifest.json",
        help="Previously generated full-source audit manifest",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Project root where samples, figures, and summary are written",
    )
    args = parser.parse_args()
    source = args.csv_path.expanduser().resolve()
    manifest_path = args.manifest.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    if not source.is_file() or not manifest_path.is_file():
        parser.error("CSV and audit manifest must both exist.")

    manifest = load_manifest(manifest_path)
    source_sha256, source_size = verify_audit(source, manifest)
    scan = sample_reservoirs(source, manifest, output_root)
    figure_dir = output_root / "docs" / "evidence" / "figures"
    figures = make_figures(manifest, scan, figure_dir, output_root)

    sample = scan["sample"]
    total = manifest["rows"]["valid_rows"]
    fraud = manifest["class_totals"]["fraud"]
    summary = {
        "eda_schema_version": 1,
        "dataset": {
            "title": manifest["dataset"]["title"],
            "source_url": manifest["dataset"]["source_url"],
            "license": manifest["dataset"]["license"],
            "source_file": source.name,
            "source_size_bytes": source_size,
            "source_sha256": source_sha256,
        },
        "figures": figures,
        "full_source": {
            "raw_rows": manifest["rows"]["data_rows"],
            "validated_rows": manifest["rows"]["valid_rows"],
            "rejected_rows": manifest["rows"]["rejected_rows"],
            "normal_rows": manifest["class_totals"]["normal"],
            "fraud_rows": fraud,
            "fraud_prevalence_percent": round(100.0 * fraud / total, 8),
            "step_min": manifest["step_range"]["min"],
            "step_max": manifest["step_range"]["max"],
            "class_counts_by_step": manifest["class_counts_by_step"],
            "quality": manifest["quality"],
        },
        "before_after": {
            "before_schema": EXPECTED_COLUMNS,
            "before_rows": manifest["rows"]["data_rows"],
            "validated_schema": EXPECTED_COLUMNS,
            "validated_rows": manifest["rows"]["valid_rows"],
            "rejected_rows": manifest["rows"]["rejected_rows"],
            "predictor_schema": FEATURE_FIELDS,
            "separate_label_schema": [LABEL_FIELD],
            "excluded_from_predictors": EXCLUDED_FEATURE_FIELDS,
            "row_policy": "No source rows are removed from the official audit.",
            "sample": sample,
        },
        "amount_dispersion_plot": {
            "measure": "log10(1 + amount)",
            "sampling": {
                "method": "Algorithm R reservoir sampling, independently counted by transaction type",
                "seed": RESERVOIR_SEED,
                "maximum_per_type": RESERVOIR_PER_TYPE,
                "sampled_per_type": scan["amount_reservoir"]["observed_per_type"],
            },
        },
        "runtime": {
            "python_version": platform.python_version(),
            "matplotlib_version": __import__("matplotlib").__version__,
        },
    }
    summary_path = output_root / "results" / "paysim-eda-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"PASS: scanned {scan['total_rows_scanned']:,} rows; rejected {scan['rejected_rows']}; step 1–2 sample {sample['rows_before']:,} rows ({sample['fraud_rows']} fraud).")
    print(f"Summary: {summary_path}")
    for figure in figures:
        print(f"Figure: {figure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
