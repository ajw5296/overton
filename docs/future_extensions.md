# Future Extensions

Tracked ideas that are out of scope for the current pipeline but worth doing later. Each entry: what it is, why it's interesting, rough mechanics, rough scale.

---

## Indirect citation traversal (1-hop forward citation cascade)

**What:** Discover policy docs that cite *papers that cite* PSU researchers — not just papers by PSU researchers directly. The relationship: `PSU paper X` → cited by → `paper Y` → cited by → `policy doc Z`.

**Why:** Captures the downstream influence of foundational PSU work. A widely-cited PSU paper might shape policy through the papers that build on it, even when policy docs don't reference PSU directly.

**Three relationships often blurred together — pick this one, the others aren't worth doing:**

| Relationship | Example | Verdict |
|---|---|---|
| **Forward citation cascade (1-hop)** | PSU X → cited by Y → policy Z cites Y | This one. Meaningful indirect impact. |
| Backward citation overlap | PSU X cites Y; policy Z also cites Y | Weak; just shared evidence base. |
| Two-hop forward | PSU X → cited by Y → cited by W → policy Z | At hop 2+ everything connects to everything. Don't do. |

**Mechanics:**
```
1. For each PSU article (~20k unique deduped):
     pull /works?filter=cites:<openalex_id> from OpenAlex (paginated)
     → discovers DOIs that cite this PSU work

2. Collect unique citing DOIs (~200-500k expected)
   Skip DOIs already in our DB (PSU works or already in any policy_doc.cites_scholarly_dois)

3. Submit remaining DOIs as Overton DOI sets:
     POST /generate_id_set.php (batches of ~1000 to stay under burst limit)
     GET /articles.php?dois=<set_id>
   → returns articles + their cited_by_documents (the new indirect policy docs)

4. For each newly-discovered policy_document_id, run Stage 4 to enrich.

5. Insert into a NEW table — keep direct vs. indirect cleanly separated:
     indirect_article_citations
       psu_doi              text     -- PSU researcher's article
       intermediate_doi     text     -- paper that cites PSU and is cited by policy
       policy_document_id   text     -- the policy doc
       citation_metadata    jsonb
       hops                 int default 1
       created_at           timestamptz
       PK: (psu_doi, intermediate_doi, policy_document_id)
```

**Rough scale:**
- ~50-100k OpenAlex calls for cited_by lookups (~2-3 hr at our rate)
- ~200-500 Overton set creations + queries (~1-2 hr if rate-limit-aware)
- Stage 4 enrichment on newly-discovered policy docs: 1-3 hr depending on count
- **Total: ~half day to a full day end-to-end**

**Dashboard impact:** add a "direct citations" vs. "extended influence (1-hop)" toggle / tab. Don't sum them on the home page metric — keep direct numbers as the headline; extended numbers as a separate rollup.

---

## Cohort expansion beyond HHD

**What:** Today's RMD cohort is 17 HHD orgs (~984 researchers). Full PSU has ~200+ orgs across ~20 colleges, projecting to ~3,000-5,000 RMD-matchable researchers.

**Why:** "PSU research impact" headline can't really be PSU-wide while we only see HHD.

**Mechanics:**
- Get expanded RMD API access (current key only sees HHD)
- Re-run `--rebuild-map` against the expanded org list — `_scan_rmd_publications()` walks whatever orgs `/organizations` returns
- Pipeline scales linearly; ~5x cohort = ~5x runtime per stage
- Storage: ~20-50k articles, ~50-100k citations (rough)

**Risk:** Overton burst limits get tighter at this scale. Will need parallel Lambda fan-out (already designed via Step Functions Map state, but Lambda zip needs to be the refactored code first — see below).

---

## Lambda zip rebuild + EventBridge re-enable

**What:** The Lambda functions and Step Functions state machine still run **pre-refactor** code. Local pipeline is the new code; deployed Lambdas are old.

**Why it matters:** The weekly EventBridge rule `overton-pipeline-weekly` (Sun 06:00 UTC) is currently **DISABLED** because firing it would re-run the old pipeline and clobber the new-shape data (we got bitten by exactly this on 2026-05-03 — old Lambda overwrote 752 researcher records back to the pre-refactor shape).

**Mechanics:**
1. Update `pipeline/lambda_handlers/*.py` if signatures changed (most should be fine)
2. `bash scripts/build_lambda_package.sh` — builds and uploads zip
3. Update each Lambda function code:
   ```bash
   for fn in overton-openalex overton-rmd overton-chunker overton-articles overton-documents overton-document-download; do
     aws lambda update-function-code --function-name "$fn" --s3-bucket overton-datalake-700032885189 --s3-key lambda-packages/pipeline-lambda.zip
   done
   ```
4. Validate by triggering a manual Step Functions execution end-to-end (small `--max-researchers`)
5. Re-enable the EventBridge rule:
   ```bash
   aws events enable-rule --region us-east-1 --name overton-pipeline-weekly
   ```

**Acceptance bar:** end-to-end Step Functions run produces the same DB state as a local `--all` run on the same date.

---

## Stage 5 PDF backfill

**What:** During the post-refactor Stage 5 run, we hit a `requests` library bug (UTF-8 decode error on a non-ASCII redirect Location header) at researcher 2,949 / 15,281. Fix is in (`document_download_stage.py` now catches `UnicodeError`), but the remaining ~12k PDFs were never attempted.

**Why:** PDF archival under our control enables future text-mining / NLP / full-text search against the policy docs. Dashboard works without them (presigned URL when available, falls back to Overton's link).

**Mechanics:** just re-run `python -m pipeline.run --stage download`. The query already filters to `download_status IN ('pending', 'failed')` and skips rows with an `s3_pdf_key`, so it'll naturally pick up the unattempted ~12k. ~8-10 hours wall clock.

**When to do:** any time. Background job overnight.

---

## ORCID API as additional works source

**What:** Pull self-reported works from ORCID's public API (`/v3.0/{orcid}/works`) per researcher and union into their DOI set.

**Why:** ORCID often catches new pubs faster than OpenAlex (researchers add their own work; OpenAlex waits on Crossref/DOAJ ingestion). Estimated coverage gain: ~5-10% more works for some researchers, especially early-career.

**Mechanics:**
- Add a small fetch in Stage 1 or Stage 2 (per researcher, when a real ORCID is available)
- Merge into `rmd.dois` (or new `orcid.dois` block) and feed into Stage 3's DOI set
- Public API, no key, simple GET

**Rough scale:** 1 call per ORCID-having researcher × ~750 = ~75 sec at 0.1s rate. Negligible.

**Caveats:** redundant with OpenAlex for ~80% of works. Prioritize after the indirect-citations work — bigger-impact for the same engineering effort.

---

## PubMed and Pure as additional sources

**What:** Direct API integration with PubMed eUtils (biomedical) and PSU Pure (institutional research info system, the backing system RMD pulls from).

**Why:**
- **PubMed**: covers conference abstracts and clinical biomedical work that OpenAlex sometimes lags on. Strong for Hershey-affiliated researchers.
- **Pure**: PSU's source-of-truth for research outputs. RMD already pulls from it, but direct Pure API access could expose internal records (theses, internal reports) RMD doesn't surface.

**Mechanics:** TBD; would need to scope each separately.

**Verdict:** hold until a specific gap motivates it. Probably won't add much beyond what OpenAlex + ORCID + RMD already give us.

---

## Better dashboard for review queues

**What:** UI for the borderline cases that currently sit as JSON files in `data/pipeline/review/`:
- `name_match_review.json` — borderline OpenAlex name-search candidates
- `oa_disambiguation_suspects.json` — researchers flagged by the disambiguation guard

**Why:** Right now these require eyeballing JSON in a text editor and manually editing the ORCID map / writing follow-up code. A "researcher resolution" dashboard page would let a human accept/reject/skip each candidate, persist the decision, and feed it back into the next pipeline run.

**Mechanics:** new Streamlit page reading the review JSONs + a small "decisions" table in the DB; pipeline reads the decisions table on subsequent runs and pre-applies the human verdicts.

**Rough scale:** small; depends on how often new review entries appear (after rebuild-map runs).
