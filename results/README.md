# Evidence directory

- paysim-audit-manifest.json records the bounded-memory audit of the official Kaggle CSV. The source CSV itself is excluded. Two full runs produced identical manifest bytes (SHA-256 `F75976A12EA2EFED92B335D60EFA312C27D1B01698CE0245D718C6C11D989790`).
- paysim-audit-repeat.json is the second full-source audit output; it matches paysim-audit-manifest.json byte for byte.
- paysim-eda-summary.json records the exact-count figures, seeded amount-reservoir settings, before/after feature schema, and two-step sample checksum.
- week2-smoke-results.json records a successful HDFS upload/read-back and Kafka produce/consume round-trip using an unlabeled event.
- toy-audit-run-a.json and toy-audit-run-b.json are identical deterministic manifests from repeated runs over the toy fixture.
- The official-source audit was run on the Kaggle CSV and repeated; the checked-in manifest contains the verified summary and per-step class counts. No raw dataset rows are included.
