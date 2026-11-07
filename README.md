# PaySim fraud detection — Hadoop MapReduce and Lambda

This is the main repository for the six-week P02 project. Its current checkpoint covers the Week 1–2 deliverables: source and architecture analysis, a full-data audit, exploratory charts, a reproducible two-step sample, Hadoop/HDFS/YARN/Kafka environment setup, and smoke evidence. Add later project components here as they are completed.

The Week 1–2 progress note separates completed work from the planned MR1/MR2, model, replay, and service stages. It records that this checkpoint was completed on an accelerated schedule.

## Status

- Week 1 data/design artifacts, official source audit, and exploratory analysis are complete. The full raw CSV is not included; its checksum and audit findings are recorded in `results/paysim-audit-manifest.json`.
- The reproducible two-step sample is published as a feature CSV plus a separate label file under `data/samples/`; it retains both classes and excludes balance fields and `isFlaggedFraud` from predictors.
- The Week 2 smoke check passed: HDFS read-back matched the uploaded file SHA-256, and Kafka returned the published unlabeled event. Evidence is in results/week2-smoke-results.json.
- The toy fixture is synthetic and is not a substitute for the official source.

See docs/progress-week1-2.md for completed, pending, and next work.

## Contents

- docs/data-and-design.md — source, license, schema, data-use policy, temporal split, and quality-audit method.
- docs/architecture.md — the P02 Lambda architecture; later layers are marked planned.
- docs/progress-week1-2.md — truthful two-week progress and a form-ready French summary.
- docs/evidence/week1-eda.md — class imbalance, fraud-by-step and amount-dispersion charts, plus before/after preparation evidence.
- scripts/audit_paysim.py — streaming CSV audit with SHA-256 and optional disk-backed exact duplicate counting.
- scripts/generate_week1_eda.py — reproducibly regenerates charts, transformation evidence, and the two-step sample from the official CSV.
- fixtures/toy_paysim.csv and fixtures/toy_expected.json — small fixture and hand-calculated reference.
- data/samples/ — small source-derived sample with predictors and labels stored separately; the full CSV remains local.
- scripts/verify_toy_fixture.py — checks the fixture against the reference values.
- environment/docker-compose.yml and its Docker build context — Hadoop/HDFS/YARN/Kafka environment, including the vendored activation API license.
- scripts/smoke_week2.ps1 — HDFS upload/read-back and Kafka produce/consume check.
- results/ — repeated official source audit manifests, EDA summary, toy-audit evidence, and HDFS/Kafka smoke-test results.

## Run the fixture check

From this directory:

~~~powershell
python scripts/verify_toy_fixture.py
~~~

Expected output:

~~~text
PASS: toy row totals, rejects, class-by-step counts, and all 11 MR1 aggregates match.
~~~

## Audit the official PaySim source

Download PS_20174392719_1491204439457_log.csv from the Kaggle page linked below using your own signed-in Kaggle session. Keep the raw CSV outside Git and run:

~~~powershell
python scripts/audit_paysim.py "C:\path\to\PS_20174392719_1491204439457_log.csv" --output results/paysim-audit-manifest.json
~~~

The checked-in manifest is from the official Kaggle CSV: it records the source size and SHA-256, validates the expected 11-column schema and row types, counts valid and rejected rows by one primary reason, reports step/class counts, and records quality summaries. The audit streams records and keeps only counters in memory; exact duplicate detection uses a temporary SQLite index on disk. No rows are removed from the source.

The manifest is deterministic for the same source bytes and audit version. It intentionally contains no run timestamp.

## Rebuild Week 1 EDA evidence

Install the plotting dependency and run the streaming analysis against the same downloaded CSV:

~~~powershell
python -m pip install -r requirements-eda.txt
python scripts/generate_week1_eda.py "C:\path\to\PS_20174392719_1491204439457_log.csv"
~~~

The script checks the CSV against the checked-in source manifest, generates the figures and before/after summary, and rebuilds the reproducible sample for steps 1–2. The sample has 3,722 rows and preserves both classes; fraud labels are written separately from its five allowed predictors. The plots use exact audited class counts and a seeded reservoir sample for the transaction-amount boxplots.

## Start the environment and run the Week 2 smoke check

Docker Desktop must be running. From this directory:

~~~powershell
docker compose -f environment/docker-compose.yml up -d --build
pwsh -File scripts/smoke_week2.ps1
~~~

The smoke script writes results/week2-smoke-results.json. It uses a unique HDFS path and Kafka topic per run. It verifies the HDFS text read-back and the exact Kafka JSON event; the event has no fraud label.

To inspect the stack:

~~~powershell
docker compose -f environment/docker-compose.yml ps
~~~

## Source and attribution

- Dataset: [Synthetic Financial Datasets For Fraud Detection (PaySim)](https://www.kaggle.com/datasets/ealaxi/paysim1), by Edgar Lopez-Rojas and collaborators.
- Kaggle lists the dataset under the **CC BY-SA 4.0** license. This snapshot includes no copied source rows other than the separately labelled project toy fixture.
- PaySim is synthetic. Its metrics must not be generalized to real financial fraud without separate evidence.
- The source description warns that fraud transactions are cancelled; the four balance fields are therefore excluded from predictive inputs.

See docs/data-and-design.md for the project’s attribution and field policy.
