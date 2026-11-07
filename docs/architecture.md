# P02 Lambda architecture

The brief calls for historical analysis and a separate replay branch. Hadoop MapReduce is the batch engine; Kafka carries replayed events. The project must not present MapReduce as streaming or call a replay a production real-time service.

The diagram distinguishes the Week 1–2 design and environment work from components scheduled for later weeks.

~~~mermaid
flowchart LR
    SRC["PaySim CSV<br/>synthetic source"]
    AUD["Week 1 audit + manifest<br/>schema, quality, checksum"]
    HDFS["HDFS / historical files"]
    MR1["MR1: account + step<br/>profiles (planned)"]
    MR2["MR2: past-only windows<br/>and versioned view (planned)"]
    PROFILE["Batch profile view<br/>versioned (planned)"]
    REPLAY["Held-out chronological<br/>replay window"]
    KAFKA["Kafka topic<br/>unlabeled events"]
    CONSUMER["Stream consumer<br/>(planned)"]
    SCORE["Rule / classical ML<br/>score (planned)"]
    SERVE["Service view + alerts<br/>(planned)"]

    SRC --> AUD
    AUD --> HDFS
    HDFS --> MR1 --> MR2 --> PROFILE
    SRC --> REPLAY --> KAFKA --> CONSUMER --> SCORE --> SERVE
    PROFILE --> SERVE
~~~

## Week 1–2 boundary

The Week 1–2 snapshot documents the source policy and architecture, packages the existing Hadoop/HDFS/YARN/Kafka Compose configuration, and provides a fixture and basic platform smoke check. The MR1/MR2 jobs, profile integration, scoring, serving, and dashboard are not claimed as Week 1–2 deliverables in this repository.

## Anti-leakage rules

1. Fit training transforms and models using only the training period.
2. Tune thresholds and select models using validation only.
3. Build every historical profile for step s from steps strictly less than s.
4. Publish isFraud only to the evaluation path, never in replay messages or scoring inputs.
5. Freeze and identify the profile/model versions used for each replay period.
6. Describe the speed branch as chronological replay with measured simulated latency, not as a live bank feed.