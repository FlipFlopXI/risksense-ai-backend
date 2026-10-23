# Drug evidence ingestion and review workflow

## Safety boundary

The five supplied version 1 JSON artifacts remain immutable inputs. Reviewed clinical evidence is published separately in `app/ml/drug_assistant/published_evidence_v1.json`. Extraction success never grants runtime eligibility. Only records explicitly marked `REVIEWED`, with reviewer metadata, an approved authoritative HTTPS source, a source revision, timestamps and a matching content hash can be loaded by `PublishedEvidenceProvider`.

The externally reviewed 931 normalized candidates for 89 medications were batch-attested and independently published on 22 September 2026. They retain `LIMITED_EVIDENCE` status. The other 119 medications remain entirely insufficient.

## Current review workspace and commands

Retrieved DailyMed SPL snapshots and MotherToBaby fact sheets are under `app/ml/drug_assistant/evidence_work/snapshots/<drug_id>/`. The resumable operation manifest is `ingestion_queue_v1.json`; normalized candidates are individual files under `evidence_work/candidates/`. Each candidate preserves the source section and excerpt, exact source URL and identifier, retrieval time, source snapshot SHA-256, a proposed extractive claim, and review fields. The source file, operation metadata, and record identity are checked again before publication.

Run from the repository root, using the project's virtual environment:

```powershell
.\.venv\Scripts\python.exe -m app.ml.drug_assistant.evidence_pipeline retrieve-dailymed --limit 10
.\.venv\Scripts\python.exe -m app.ml.drug_assistant.evidence_pipeline retrieve-mothertobaby --limit 10
.\.venv\Scripts\python.exe -m app.ml.drug_assistant.evidence_normalization
.\.venv\Scripts\python.exe -m scripts.review_drug_evidence --summary
.\.venv\Scripts\python.exe -m scripts.review_drug_evidence --drug metformin --pending
.\.venv\Scripts\python.exe -m scripts.review_drug_evidence --drug metformin --pending --interactive --reviewer "Your name"
.\.venv\Scripts\python.exe -m scripts.publish_drug_evidence --drug metformin
.\.venv\Scripts\python.exe -m scripts.review_drug_evidence --approve-all-pending --reviewer "Reviewer name" --attest-reviewed --dry-run
.\.venv\Scripts\python.exe -m scripts.review_drug_evidence --approve-all-pending --reviewer "Reviewer name" --attest-reviewed
.\.venv\Scripts\python.exe -m scripts.publish_drug_evidence --all-reviewed
.\.venv\Scripts\python.exe -m app.ml.drug_assistant.evidence_pipeline coverage
```

Retrieval is optional when snapshots already exist. Normalization resumes without overwriting existing candidate review decisions. The review CLI accepts `--topic`, `--source`, `--group`, `--pending`, `--reviewed`, and `--conflicts` filters. Interactive review shows each exact candidate and requires an explicit A (approve), P (partial), or R (reject) confirmation for that evidence ID. S/N skips; V repeats the source/provenance view. Batch attestation is only for a reviewer who has already reviewed the exact existing candidate set externally; it requires a dry run, explicit attestation, exact-count confirmation, and a candidate backup.

For a `PARTIAL` DailyMed operation, list the recorded labels with:

```powershell
.\.venv\Scripts\python.exe -m scripts.review_drug_evidence --drug metformin --select-product --reviewer "Your name"
```

After checking ingredient, formulation, route, and current human prescription status, explicitly select one recorded SET ID:

```powershell
.\.venv\Scripts\python.exe -m scripts.review_drug_evidence --drug metformin --select-product --set-id "<verified-set-id>" --reason "<why this exact label fits>" --reviewer "Your name"
```

The product list is sorted deterministically and flags name mismatches, non-human labels and combination products that do not match a single-ingredient catalogue entry. Those mismatches cannot be selected. The command retrieves only the exact confirmed SET ID, records the selection reason, and normalizes its available sections. No product is chosen automatically. Metformin's current MotherToBaby snapshot yields general information, pregnancy, lactation, and fertility candidates. Its adverse effects, warnings, interactions, and monitoring remain gaps until an appropriate source is selected and those sections are present.

After explicit approval, publication validates the candidate's reviewer, timestamp, canonical record hash, catalogue ID, source URL/organisation, current queue operation, original snapshot hash, section, and excerpt. It publishes only `REVIEWED` records and regenerates `published_evidence_v1.json` and `evidence_coverage_v1.json`. Restart API workers after publication because the published store is cached per process. Verify with `/admin/drug-assistant/status` and a real, authorized Drug Assistant question; a topic still without reviewed evidence remains insufficient.

## Source hierarchy

1. Tier 1: FDA-approved labeling/current DailyMed SPL and official regulator labeling.
2. Tier 2: MotherToBaby, NHS/Specialist Pharmacy Service, WHO and recognized professional clinical organizations where the topic fits their remit.
3. Tier 3: another source only after its organization and domain are explicitly approved in code and review policy.

Anonymous sites, forums, social media, marketing pages, arbitrary search results and AI-generated medical pages are prohibited. DailyMed provides a versioned, GET-only API for current SPL documents. A DailyMed SET ID and label revision should be retained so a changed SPL can be detected. Pregnancy records follow FDA PLLR sections 8.1 Pregnancy, 8.2 Lactation, and 8.3 Females and Males of Reproductive Potential; obsolete A/B/C/D/X categories are not the primary representation.

## Evidence record

Each published record identifies one catalogue `drug_id`, topic/subtopic, a short reviewed paraphrase, optional related drug IDs, source organization/title/URL/identifier/section/revision date, retrieval and review timestamps, reviewer/mechanism, evidence revision, integrity hash, evidence state, population, pregnancy timing, lactation relevance and notes.

Interaction records represent a supported pair or small source-defined set through `drug_id` plus `related_drug_ids`. They do not create a 208 × 208 table. Runtime compares an explicitly resolved medicine with other resolved medicines or authorized active patient medication records. Uncovered pairs are returned as unavailable; they are never described as having no interaction.

## Commands

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m app.ml.drug_assistant.evidence_pipeline bootstrap
.\.venv\Scripts\python.exe -m app.ml.drug_assistant.evidence_pipeline coverage
```

`bootstrap` creates or resumes 416 operations: DailyMed and MotherToBaby checks for each of 208 medications. Existing operation results are preserved. Each operation records one of `SUCCESS`, `PARTIAL`, `NO_SOURCE`, `FAILED`, or `REQUIRES_REVIEW`; the initial queue uses `REQUIRES_REVIEW` because no source-specific extraction has been medically reviewed.

DailyMed retrieval is opt-in and bounded:

```powershell
.\.venv\Scripts\python.exe -m app.ml.drug_assistant.evidence_pipeline retrieve-dailymed --limit 10
```

The adapter uses DailyMed's fixed HTTPS v2 service, rejects arbitrary URLs and oversized responses, records SET ID/revision/hash, and stores the SPL only in the review workspace. Zero matches become `NO_SOURCE`; multiple labels become `PARTIAL` and require human product selection; failures are retryable. A successful download is still unreviewed and never enters runtime automatically.

An extraction adapter may locate and download permitted source material into a non-runtime review workspace, map likely sections and compute source hashes. It must leave proposed records at `INGESTED`, `VALIDATED_STRUCTURE`, or `REVIEW_REQUIRED`. It must not set `REVIEWED`.

A qualified review process must:

1. Confirm the source identifies the correct active ingredient/product and is current.
2. Compare every paraphrase with the cited source section.
3. Confirm topic, population, timing and related-drug mappings.
4. Record the reviewer and review mechanism.
5. Set `reviewed_at`, `review_state=REVIEWED`, revision and the canonical content hash.
6. Submit the package to the publisher:

```powershell
.\.venv\Scripts\python.exe -m app.ml.drug_assistant.evidence_pipeline publish path\to\reviewed-package.json
```

The publisher rejects unreviewed records, unapproved domains, future or absent timestamps, unknown catalogue IDs, invalid pairs, duplicate IDs and changed content hashes. It writes a deterministic published store and immediately reloads it through the production validator.

The legacy `scripts/drug_evidence_review.py` workbench remains available for individual source-specific drafts, but it no longer publishes on approval. The primary grouped review workflow is `scripts.review_drug_evidence` above. Both avoid hand-editing the publication store:

```powershell
.\.venv\Scripts\python.exe -m scripts.drug_evidence_review queue --status SUCCESS
.\.venv\Scripts\python.exe -m scripts.drug_evidence_review list --drug-id metformin --topic pregnancy
.\.venv\Scripts\python.exe -m scripts.drug_evidence_review draft --drug-id metformin --source-family MOTHERTOBABY --topic pregnancy --subtopic pregnancy --claim "<reviewed paraphrase>" --source-title "<source title>" --source-section "<exact section>"
.\.venv\Scripts\python.exe -m scripts.drug_evidence_review approve <evidence-id> --reviewer "<reviewer identity>" --notes "<review notes>"
```

Use `partial` for limited evidence or `reject` when the draft must not be published. Every decision requires an explicit reviewer. Approval records review state; the separate publisher validates source domain, record state, catalogue identity, snapshot provenance and content hash.

After publication, regenerate `evidence_coverage_v1.json`. Coverage is derived from actual eligible records. A missing domain remains `INSUFFICIENT_EVIDENCE`; partially populated domains remain `PARTIAL`. A source change requires a new extraction hash/revision and human re-review. Materially changed content must not reuse its prior reviewed hash.

## Completed source processing

All 416 planned operations were attempted. DailyMed produced 7 `SUCCESS`, 193 `PARTIAL` and 8 `NO_SOURCE` results. MotherToBaby produced 87 `SUCCESS`, 1 `PARTIAL`, 119 `NO_SOURCE` and 1 `FAILED` result. The failure is `nortriptyline` from MotherToBaby with `SOURCE_RETRIEVAL_FAILED`. Normalization processed all 208 medications and created 931 candidates (877 MotherToBaby, 54 DailyMed) for 89 medications. After the reviewer's explicit external attestation, all 931 passed validation and publication. The 193 ambiguous DailyMed operations remain unresolved; 119 medications have no evidence candidate.

### September 2026 expansion run

The conservative resolver re-queried all 193 ambiguous DailyMed operations with paginated search results and selected only one unique, SPL-verified human prescription, single-ingredient product: `bempedoic_acid` (SET ID `88d06d89-a3da-40b4-b273-8f4f7d56c4c9`). Of the original 193, 192 remain `PARTIAL`; 189 were classified ambiguous in this run, two searches failed, and one product failed metadata verification. The eight original `NO_SOURCE` entries remain. The selected SPL is stored with its revision, retrieval time and SHA-256. Full candidate details are in the resolution run JSON; a concise view is in `DAILYMED_PRODUCT_RESOLUTION_REPORT.md`.

Full-catalogue normalization produced 147 **new** `REVIEW_REQUIRED` records across eight medications. The existing 931 `REVIEWED` candidates and 931 published records remain untouched. The generated `DRUG_ASSISTANT_NEW_EVIDENCE_REVIEW.md` groups each new candidate by medicine, topic and section and shows source excerpt and provenance verification. The manifest at `app/ml/drug_assistant/evidence_work/expansion_review_manifest_v1.json` fixes this batch's exact candidate IDs so later review cannot accidentally include old or later records.

**Publication update:** Shiven Reddy explicitly approved all 147 records in that manifest after external review. The manifest-scoped dry run found 147 eligible and no invalid, ambiguous or unrelated candidates. Batch attestation backed up the candidate state and moved exactly 147 to `REVIEWED`, with zero failures. The independent publisher accepted all 1,078 reviewed candidates, rejected none, and regenerated coverage. The current store has 1,078 `LIMITED_EVIDENCE` records across 90 medicines. No candidates remain pending in this queue; 118 medicines still have no published evidence. The commands below document the completed workflow and should not be rerun as a new approval.

Use the manifest for individual interactive review:

```powershell
.\.venv\Scripts\python.exe -m scripts.review_drug_evidence --manifest app/ml/drug_assistant/evidence_work/expansion_review_manifest_v1.json --pending --interactive --reviewer "Shiven Reddy"
```

After reviewing the entire generated report externally, run the manifest-scoped dry run, then explicitly attest only the reviewed candidates:

```powershell
.\.venv\Scripts\python.exe -m scripts.review_drug_evidence --manifest app/ml/drug_assistant/evidence_work/expansion_review_manifest_v1.json --approve-all-pending --attest-reviewed --reviewer "Shiven Reddy" --dry-run
.\.venv\Scripts\python.exe -m scripts.review_drug_evidence --manifest app/ml/drug_assistant/evidence_work/expansion_review_manifest_v1.json --approve-all-pending --attest-reviewed --reviewer "Shiven Reddy"
.\.venv\Scripts\python.exe -m scripts.publish_drug_evidence --all-reviewed
.\.venv\Scripts\python.exe -m app.ml.drug_assistant.evidence_pipeline coverage
```

The non-dry attestation requires exact-count confirmation and writes a backup. Only a person who has actually reviewed each claim against its source should run it. Restart API workers after publication; the provider caches the published store. Re-test authorized chat questions and `/admin/drug-assistant/status` afterward.

## Runtime validation

The runtime resolves medication and intent before evidence retrieval. `PublishedEvidenceProvider` reads only reviewed records and combines them with the legacy reviewed-cache provider for compatibility. Response validation then checks resolved drug identity, intent/topic domain, pregnancy/lactation separation and claim-to-citation membership. A validation failure removes claims and citations, returns `INSUFFICIENT_EVIDENCE`, and emits `DRUG_RESPONSE_VALIDATION_FAILED` when the turn is persisted.
