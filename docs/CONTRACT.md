# Data Contract — v1.1

This is the single source of truth for data shapes shared between the backend
pipeline and the report frontend. **Any change here is a contract change:** bump
the version, update `backend/yks_institutional/schemas.py`, and share with all
parties before coding against it.

## Conventions

YKS Radar — Institutional backend schemas (CONTRACT v1.0).

This file is the single source of truth for data shapes. Any change here is a
contract change: bump CONTRACT_VERSION and share with all parties (frontend /
report work builds against these shapes).

Conventions (project-wide, do not violate):
  * Lower rank number = better, everywhere.
  * rank_margin = student_rank - threshold  (negative = student is competitive).
  * Warnings are never silent: every anomaly becomes a Warning surfaced upward.
  * IRT columns exist but are nullable — v1 fills classical stats only.

## Report payload shapes (frontend reads these verbatim)

The three report components consume exactly these shapes, produced by
`backend/yks_institutional/reports/data.py`. If a report needs a field not
present here, that is a v2 ticket — not a frontend workaround and not a silent
schema change.

### student_report(db, student_id)
```json
{
  "student_id": "uuid",
  "n_exams": 3,
  "exams": [{
    "exam_id": "uuid",
    "tyt_net": 57.5, "ayt_net": 0.0,
    "subjects": [{"subject": "TYT Matematik", "net": 16.5,
                  "correct": 21, "wrong": 18, "blank": 1}]
  }],
  "strengths":   [{"subject": "TYT Türkçe", "level": 61,
                   "class_average": 48, "based_on_exams": 3}],
  "focus_areas": [{"subject": "TYT Fen", "level": 34,
                   "class_average": 45, "based_on_exams": 3}]
}
```
`level` / `class_average` are plain 0–100 scales — never percentiles or thetas
in user-facing copy.

### rank prediction (joined into the student report header)
```json
{
  "score_type": "SAY",
  "rank_low": 95000, "rank_mid": 110000, "rank_high": 130000,
  "flags": ["obp_missing_estimate_incomplete"]
}
```
Only warning-class flags mark the estimate incomplete. Info-class flags (e.g.
`obp_autoconverted_from_diploma_note`) are calm notices, not alarms.

### teacher_report(db, exam_ids)
```json
{
  "timeline": [{"exam_id": "uuid", "topics": {"Geometri": 42}}],
  "trends": [{"topic": "Geometri", "change": -9,
              "direction": "declining", "from": 51, "to": 42}]
}
```
`topics` values are 0–100. Only |change| ≥ 5 surfaces in `trends`. Topic sets
may differ across exams — the union is taken; missing values render as blanks.

### principal_dashboard(db, school_id, exam_ids)
```json
{
  "school_id": "uuid", "as_of": "2026-07-21",
  "exams": [{"exam_id": "uuid", "n_students": 200,
             "tyt_net_mean": 34.6, "tyt_net_median": 34.0,
             "tyt_net_p25": 18.8, "tyt_net_p75": 51.2}],
  "trajectory": {"tyt_net_change": 13.3, "direction": "up"}
}
```
`trajectory` is `null` when fewer than two exams exist. `direction` is one of
`up | down | flat`; unknown values degrade to a neutral banner.

## Pending contract additions (v1.2)

- **placement band** on the rank prediction: `"strong" | "balanced" | "reach"`
  with Turkish labels, derived from `rank_margin` against the department
  forecasts. Feeds the student report's `placementOutlook` prop, which today
  shows a neutral "Hazırlanıyor" state until this lands.
