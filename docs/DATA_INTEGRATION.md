# Data Integration Guide

Two integrations are pending and both are gated on inputs only you can provide.
This is the checklist for when they arrive.

## 1. Wire the real score→rank engine (~30 min)

Today, predictions run through `PlaceholderEngine`
(`calibration/predict.py`), stamped `PLACEHOLDER_DO_NOT_SHIP`. Its curve is
monotone and convention-correct but **not calibrated** — never show its output
to a user.

Replace it with a thin adapter around the existing YKS Radar score/rank engine:

```python
from yks_radar.integrated_api import IntegratedAPI   # existing project code

class RealEngine:
    engine_name = "yks_radar_integrated_v1"
    def __init__(self):
        self.api = IntegratedAPI()
    def score(self, tyt_net, ayt_net, obp, score_type):
        return self.api.compute_score(tyt_net=tyt_net, ayt_net=ayt_net,
                                      obp=obp, score_type=score_type)
    def rank_for_score(self, score, score_type):
        return self.api.rank_from_score(score, score_type)
```

Pass `RealEngine()` to `predict_and_log`. Every prediction records which engine
produced it (`RankPrediction.engine`), so placeholder rows stay identifiable
and excludable. The placement engine and the 114 department forecasts consume
`rank_mid / rank_low / rank_high` unchanged.

## 2. Bring the first real school files

The ingestion pipeline already handles two upload shapes; confirm which yours
match and adjust nothing until a real file proves otherwise:

- **Wide grid** — one row per student, one column per question (plus a student
  number column; answer key may be an embedded row or supplied separately).
- **Long format** — `student_no, question_no, answer`, one row per response.

Auto-detected notations: `A–E`, `1–5`, and (with an explicit flag) Turkish
`D/Y`. Turkish encodings (`iso-8859-9`) are handled.

Per-upload call:

```python
from yks_institutional.ingestion.pipeline import SubjectBlock, ingest_upload

outcome = ingest_upload(
    db, school_id=..., file_bytes=..., filename=...,
    exam_name=..., exam_date=...,
    subject_blocks=[SubjectBlock(Subject.TYT_TURKCE, 1, 40), ...],
    answer_key=None,                 # None if embedded in the file
    topics={1: "Paragraf", 61: "Geometri", ...})   # optional, unlocks teacher trends
if outcome.accepted:
    refresh_school_abilities(db, school_id)
# ALWAYS surface outcome.warnings — that's the trust surface with schools.
```

### What to watch on first contact with real data

1. **Column headers** — real exports use names our aliases may not cover yet.
   If matching fails, add the header string to the alias sets in
   `ingestion/adapters.py` (wide) or `ingestion/long_format.py` (long).
2. **Subject blocks** — you must tell the pipeline which question positions map
   to which subject. Get this from the exam's structure, not guessed.
3. **Topic map** — the single highest-value extra input. `topics={position:
   name}` upgrades teacher trends from subject-level to topic-level
   ("Geometri declining"). Bring one real exam's topic map to prove the path.
4. **AYT files** — fully supported by schemas and blocks, but so far exercised
   only by unit tests. Run a real AYT file through early.

## 3. Feed the reports from live data

Once real exams are ingested, replace the report components' embedded sample
data with live payloads:

```python
from yks_institutional.reports.data import (
    student_report, teacher_report, principal_dashboard)

student_report(db, student_id)              # -> StudentReport.jsx props
teacher_report(db, exam_ids)                # -> TeacherReport.jsx props
principal_dashboard(db, school_id, exam_ids)  # -> PrincipalDashboard.jsx props
```

The shapes match `docs/CONTRACT.md` exactly. The seam to watch: the components'
flag handling keys off the real `WarningCode` values — verify the flags your
pipeline actually emits are the ones the components style.

## Privacy note

Real student data must never enter git. `.gitignore` already blocks `*.xlsx`,
`*.csv`, `*.sqlite3`, and `/data/`, `/uploads/` (test fixtures excepted). Keep
real files outside the repo tree or in an ignored `/data/` directory.
