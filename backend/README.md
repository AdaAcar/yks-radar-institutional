# YKS Radar — Institutional Backend (v1)

Days 1–7 of the 14-day plan, delivered as one tested package: schemas, SQLite
store, ingestion (3 formats), matching, validation, knowledge-layer v0
(classical item stats), ability estimation with shrinkage, prediction hook,
residual ledger, and report data endpoints. **41/41 tests passing.**

## Quick start
```bash
pip install pydantic openpyxl pytest
python -m pytest yks_institutional/tests/ -q      # 37 passed
python -m yks_institutional.demo                   # full end-to-end run
```

## Package map
```
schemas.py               CONTRACT v1.0 — every shape, all conventions in docstring
db.py                    SQLite layer (Postgres-portable SQL)
ingestion/adapters.py    CSV/XLSX parsing, notation auto-detect (A-E / 1-5 / T-F, Turkish)
ingestion/matching.py    student no -> UUID; zero-pad tolerant; fuzzy-name fallback
ingestion/validation.py  duplicates, key mismatches, chance-level & uniform-answer flags
ingestion/pipeline.py    ingest_upload(): bytes -> persisted exam/results/item stats
stats/classical.py       p-value + corrected point-biserial per question
stats/ability.py         shrunk net-fraction estimator + refresh_school_abilities()
calibration/predict.py   predict_and_log(): ability -> nets -> score -> rank + residual
reports/data.py          student / teacher / principal JSON payloads
seed_synthetic.py        200-student synthetic school, emits raw files in 3 formats
demo.py                  python -m yks_institutional.demo
```

## The one thing you must do before any user sees output
`calibration/predict.py` ships with `PlaceholderEngine`
(`engine_name = "PLACEHOLDER_DO_NOT_SHIP"`). Its score→rank curve is monotone
and convention-correct but **not calibrated**. Replace it with a thin adapter
around the existing integrated API — the exact snippet is in
`wire_real_engine()`'s docstring. Every prediction records which engine
produced it, so placeholder rows are identifiable and excludable later.

## Conventions (enforced in code and tests)
- Lower rank number = better, everywhere. `rank_low` is the better boundary.
- `rank_margin = student_rank − threshold`; negative = competitive.
- Nothing fails silently: every anomaly is an `IngestWarning` with severity;
  FATAL rejects the upload atomically, everything else imports and surfaces.
- OBP: diploma notes (≤100) auto-convert ×5 floored at 250 with a flag; blank
  contributes exactly zero with `obp_missing_estimate_incomplete`. No phantom 350.
- IRT columns (`irt_difficulty`, `irt_discrimination`) exist and are **never
  written** in v1 — the future estimator lands without a migration.

## Why the ability model is deliberately simple
Per-student data is sparse (1–5 mocks). The shrinkage estimator
(`theta = (n·raw + K·cohort_mean)/(n+K)`, K=1.5) is the same lesson as
`forecast_threshold.py`: aggressive individual estimates lose to shrunk ones
until data volume says otherwise. The `AbilityEstimate.method` field versions
the estimator so IRT can replace it behind the same schema.

## The residual ledger is the moat
`predict_and_log()` opens a residual row (null outcome) for every prediction.
When official results arrive: `db.record_outcome(student_id, actual_rank,
source="user_official_result")` — the 4×-weight source class from the core
calibration module. `residual_summary()` gives MAE + interval coverage, the
same metrics as `backtest.py`. Start logging on day one; the calibration work
in months 2–12 trains on this table.

## Handoff shapes for the frontend (ChatGPT side)
Reports read exactly these payloads — if a report needs a field not present,
that is a contract change routed through Dinç, not a frontend hack.

- `student_report(db, student_id)` → `{exams: [{tyt_net, ayt_net, subjects:
  [{subject, net, correct, wrong, blank}]}], strengths: [{subject, level,
  class_average, based_on_exams}], focus_areas: [...], n_exams}`
  ("level" is a plain 0–100 scale; no SEs in user-facing copy.)
- `teacher_report(db, exam_ids)` → `{timeline: [{exam_id, topics: {name: 0–100}}],
  trends: [{topic, change, direction, from, to}]}` — "geometry declining" is a
  p-value delta; only |Δ| ≥ 5 points surfaces.
- `principal_dashboard(db, school_id, exam_ids)` → per-exam
  mean/median/p25/p75 TYT nets + trajectory direction.

## Per-upload flow (what the API route will call)
```python
outcome = ingest_upload(db, school_id=..., file_bytes=..., filename=...,
                        exam_name=..., exam_date=...,
                        subject_blocks=[SubjectBlock(Subject.TYT_TURKCE, 1, 40), ...],
                        answer_key=None)          # None if embedded in file
if outcome.accepted:
    refresh_school_abilities(db, school_id)
# always show outcome.warnings to the uploader — that's the trust surface
```

## Merged from the ChatGPT deliverable (v1 → v1.1)
After review of `yks_radar_institutional_v1_refined.zip`, the following were
ported in (its strongest ideas), on top of this package as the base:
- **Model-level validators**: net ≡ correct − wrong/4, rank interval ordering
  enforced at construction — invalid states are unrepresentable.
- **`sample_weight` on residuals**: `record_outcome()` defaults official
  results to 4.0 (core calibration convention); `residual_summary()` now also
  reports `weighted_mae`.
- **Long-format ingestion** (`ingestion/long_format.py`): row-per-response
  files (some optic/publisher exports) auto-detected structurally and pivoted
  into the same pipeline. Both formats, one code path.
- **Extended enums**: AYT sözel subjects (Tarih-2, Coğrafya-2, Felsefe, Din)
  with official question counts, plus a `ScoreType` enum (SAY/EA/SÖZ/DİL).
- **Audit + future-proofing**: `raw_answer` column on responses (populated by
  the long path; wide path stores canonical only), `irt_guessing` (3PL-ready,
  never written in v1), `schema_version` table.

Not merged, with reasons: its long-only ingestion (wide grids are what schools
actually export — kept mine as primary), its per-exam calibration (no
cross-exam aggregation, no SE, cohort mean pooled across exams of different
difficulty — kept the shrinkage aggregator), its point-only residuals (can't
compute interval coverage — kept interval bounds), and its required raw `obp:
float` (regresses the OBP diploma-note fix — kept `normalize_obp`).

## Known gaps (deliberate, for days 8–14)
- Real engine wiring (see above) — blocks demo, 30 minutes once repo is joined.
- Topic tags per question: `ingest_upload(topics={position: "Geometri", ...})`
  is supported; needs the topic map per exam from real data. Teacher trends
  fall back to subject level without it.
- HTTP layer: functions are route-shaped; FastAPI wrapper is ~1 hour.
- AYT ingestion: fully supported by schemas/blocks, exercised only by unit
  tests so far — run a real AYT file through when you have one.
- Optic reader / MEB formats: adapter interface is stable; add parsers as
  real sample files arrive.
