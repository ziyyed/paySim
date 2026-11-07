# Progress for the Weeks 1–2 checkpoint

This note follows the six-week plan in the P02 brief and reports only the Week 1–2 deliverables. They were completed in an accelerated schedule; this checkpoint does not claim the work took exactly two calendar weeks.

## Week 1 — data and design

**Completed in this snapshot**

- Reviewed the P02 source, schema, leakage constraints, temporal evaluation requirements, and Lambda components.
- Documented the Kaggle source and listed CC BY-SA 4.0 license, the 11 expected columns, field-use policy, chronological split rationale, and architecture.
- Downloaded and audited the official Kaggle CSV locally. The schema and column order match all 11 expected columns; all 6,362,620 rows pass validation, with zero rejected rows. The step range is 1–743, with 6,354,407 normal and 8,213 fraud rows. The source checksum and per-step class counts are in `results/paysim-audit-manifest.json`.
- Implemented a bounded-memory audit utility for file size, SHA-256, schema, row validation, rejection reasons, step/class counts, and quality summaries.
- Added a toy fixture and independently hand-calculated account/step references for the audit and first batch-aggregation logic.

**Carried forward**

- Exact temporal split boundaries remain to be selected and recorded before later batch/model work. No temporal split or model is claimed as a Week 1–2 result.

## Week 2 — environment and test data

**Completed in this snapshot**

- Packaged the project’s existing Docker Compose configuration for Hadoop/HDFS/YARN and Kafka.
- Added and ran a basic smoke check. HDFS returned the uploaded file unchanged, with matching SHA-256 hashes; Kafka returned the exact event published to a new topic, with no fraud label. Runtime evidence is in results/week2-smoke-results.json.

## Plan for the next two weeks (Weeks 3–4)

- **Week 3 / MR1:** implement the Java Hadoop job that aggregates transaction counts, sums, maxima, and types by synthetic sender account and step; count malformed/rejected records; validate at least three hand-calculated account references on Hadoop/YARN.
- **Week 4 / MR2:** implement historical features using steps strictly earlier than the scored step; handle missing steps and accounts with no history; export a versioned batch view; test that changing a future transaction cannot change an earlier profile.
- Preserve the temporal boundaries and source manifest in later experiments. These items are planned work and are not represented as completed in this Week 1–2 snapshot.

## Form-ready summary (French)

**Tâches réalisées au cours des deux dernières semaines**
- Analyse du cahier des charges P02 et formalisation du schéma PaySim, des champs interdits au scoring, de la séparation temporelle et de l’architecture Lambda.
- Téléchargement local et audit en flux du CSV PaySim officiel : 6 362 620 lignes valides, 0 rejet, 11 colonnes conformes, 8 213 fraudes et étapes observées de 1 à 743; le CSV brut n’est pas publié.
- Création d’un jeu de données jouet avec résultats calculés à la main; sa vérification et les audits répétés sont reproductibles.
- Préparation de la configuration Docker Compose Hadoop/HDFS/YARN/Kafka; vérification réussie du dépôt/lecture HDFS et de la publication/consommation Kafka d’un événement sans étiquette.

**Résultats vérifiés**
- L’empreinte SHA-256 et les comptes détaillés par étape sont dans `results/paysim-audit-manifest.json`; le CSV brut reste local.
- La preuve du contrôle HDFS/Kafka réussi est incluse dans le dépôt.

**Tâches planifiées pour les deux prochaines semaines**
- Développer et valider MR1 en Java sur Hadoop/YARN avec des agrégats de référence calculés à la main.
- Développer MR2 avec des fenêtres strictement passées, tester l’absence de fuite temporelle et exporter une vue batch versionnée.

**Blocages ou aide nécessaire**
- Aucun blocage technique pour les livrables des semaines 1–2. La prochaine étape du projet est le développement de MR1 en semaine 3.
