# PaySim fraud detection — Week 1–2 snapshot

This repository is a scoped snapshot of the first two weeks in the P02 brief. It contains the dataset/design work, a streaming source-audit utility, the hand-checkable toy fixture, the existing Hadoop/HDFS/YARN/Kafka environment configuration, and a basic HDFS/Kafka smoke check.

**This is not the complete six-week project.** It does not claim Week 3–6 MapReduce, ML, scoring, service, dashboard, or benchmark work as Week 1–2 accomplishments.

## Status

- Week 1 design artifacts and the official source audit are complete. The raw CSV is not included; its checksum and audit findings are recorded in `results/paysim-audit-manifest.json`.
- The Week 2 smoke check passed: HDFS read-back matched the uploaded file SHA-256, and Kafka returned the published unlabeled event. Evidence is in results/week2-smoke-results.json.
- The toy fixture is synthetic and is not a substitute for the official source.

See docs/progress-week1-2.md for completed, pending, and next work.

## Contents

- docs/data-and-design.md — source, license, schema, data-use policy, temporal split, and quality-audit method.
- docs/architecture.md — the P02 Lambda architecture; later layers are marked planned.
- docs/progress-week1-2.md — truthful two-week progress and a form-ready French summary.
- scripts/audit_paysim.py — streaming CSV audit with SHA-256 and optional disk-backed exact duplicate counting.
- fixtures/toy_paysim.csv and fixtures/toy_expected.json — small fixture and hand-calculated reference.
- scripts/verify_toy_fixture.py — checks the fixture against the reference values.
- environment/docker-compose.yml and its Docker build context — Hadoop/HDFS/YARN/Kafka environment, including the vendored activation API license.
- scripts/smoke_week2.ps1 — HDFS upload/read-back and Kafka produce/consume check.
- results/ — repeated official source audit manifests, toy-audit evidence, and HDFS/Kafka smoke-test results.

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

