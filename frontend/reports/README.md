# Report Components

Three self-contained React components for the institutional reports. Each is a
single `.jsx` file with embedded sample data, no external fetches, no browser
storage. Drop into a React app and it renders; pass the matching payload from
the backend's `reports/data.py` as props for live data.

## Components

### `StudentReport.jsx`
Props: `studentReport`, `rankPrediction`, `placementOutlook` (optional).
Shows exam-by-exam net progression, per-subject breakdown, strengths and focus
areas, and the rank interval. Warning-class flags render an amber "incomplete"
banner; info-class flags (e.g. OBP auto-converted) render a calm blue notice.
The placement band ("Yerleşme görünümü") shows only when `placementOutlook` is
supplied by the placement engine — otherwise a neutral "Hazırlanıyor" state.
Print-ready (A4).

### `TeacherReport.jsx`
Props: `teacherReport`.
Class-level topic trends over time, plus a "latest exam" panel and a
gaining/declining trend list (only ≥5-point moves, filtered upstream). Topic
sets may differ across exams; missing values render as "—". Print-ready.

### `PrincipalDashboard.jsx`
Props: `principalDashboard`.
School TYT distribution (mean / median / p25–p75) per exam, trajectory
direction, and per-exam participation with a small-group flag (<30 students).
Null trajectory and unknown directions degrade to honest banners. Print-ready.

## Data shapes

All payload shapes are documented in [`../../docs/CONTRACT.md`](../../docs/CONTRACT.md)
and produced verbatim by `backend/yks_institutional/reports/data.py`.

## Copy rules (product requirement)

User-facing copy is plain Turkish. No standard errors, z-scores, or confidence
coefficients anywhere a student or parent can see. Uncertainty is always a
plain range. Ranks: lower number = better. No guarantee of placement — the
outlook uses soft bands.

## Constraints

React function components, hooks only, single file each, default export, no
required props (embedded defaults), Tailwind core utility classes only, no
`<form>` tags, no `localStorage`/`sessionStorage`. SVG `<title>` tooltips use
template strings (React rejects mixed text+expression children).

## Print / PDF

Print styling lives inside each component (a `PrintStyles` block + `print:`
utilities) — there are no separate `_print.jsx` files, deliberately: one source
of truth per component. Use the browser's Print → Save as PDF.
