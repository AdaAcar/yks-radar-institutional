# YKS Radar — Institutional

School mock-exam ingestion, student ability calibration, university-placement
prediction, and institutional reporting for the Turkish university entrance
exam (YKS). This repo holds the **institutional** layer: everything that turns
a school's uploaded mock-exam results into per-student rank predictions and
into reports for students, teachers, and principals.

## Status

| Component | State | Tests |
|---|---|---|
| Backend pipeline (ingest → calibrate → predict → report data) | v1.1, working end-to-end | 41/41 passing |
| Report frontend (student / teacher / principal, print-ready) | 3/3 delivered, render-verified | — |
| Real score→rank engine wiring | **pending** — placeholder in place | — |
| Real-data integration | **pending** — awaiting first school files | — |

The backend runs today on synthetic data (`python -m yks_institutional.demo`).
Two things are deliberately not done yet and are gated on real inputs: wiring
the existing YKS score/rank engine (a ~30-minute adapter, see
`docs/DATA_INTEGRATION.md`), and running real school files through ingestion.

## Structure

```
backend/                     Python package (Pydantic + SQLite, zero-ops)
  yks_institutional/
    schemas.py               CONTRACT v1.1 — every data shape + conventions
    db.py                    SQLite store (Postgres-portable SQL)
    ingestion/               CSV/XLSX adapters, matching, validation, pipeline
    stats/                   classical item stats + shrinkage ability estimator
    calibration/             prediction hook + residual ledger (the moat)
    reports/                 student / teacher / principal JSON endpoints
    seed_synthetic.py        200-student synthetic school, 3 formats
    demo.py                  end-to-end runnable demo
    tests/                   41 tests
  pyproject.toml
  README.md                  backend deep-dive + merge notes

frontend/reports/            Self-contained React report components (.jsx)
  StudentReport.jsx          rank interval, subject breakdown, focus areas
  TeacherReport.jsx          class topic trends over time
  PrincipalDashboard.jsx     school distribution + trajectory
  README.md                  props, data shapes, embedding notes

docs/
  CONTRACT.md                the data contract shared across backend & frontend
  DATA_INTEGRATION.md        how to plug in the real engine + real school files
```

## Quickstart

```bash
cd backend
python -m pip install -e ".[dev]"
pytest                              # 41 passed
python -m yks_institutional.demo    # seeds a synthetic school, prints reports
```

The report components are self-contained: drop any `.jsx` into a React app and
it renders with embedded sample data, or pass the matching payload from
`reports/data.py` as props.

## Conventions (enforced in code and tests)

- Lower rank number = better, everywhere. `rank_low` is the better boundary.
- `rank_margin = student_rank − threshold`; negative = competitive.
- Nothing fails silently: every ingest anomaly is a surfaced warning.
- OBP: diploma notes (≤100) auto-convert ×5 floored at 250; blank contributes
  zero with a flag. No phantom values.
- IRT columns exist but are never written in v1 — future estimators land
  without a migration.

## Roadmap (next)

1. Wire the real score→rank engine (`docs/DATA_INTEGRATION.md`).
2. Contract v1.2: placement band from `rank_margin` → the student report's
   `placementOutlook` prop.
3. Real-data integration pass: first school files through ingestion; feed the
   three report components from live `reports/data.py` output.
4. FastAPI layer over the ingest + report functions.

## License

Private / proprietary — all rights reserved (update as needed).
