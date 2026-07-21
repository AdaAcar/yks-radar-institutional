"""End-to-end demo: synthetic school -> 3 uploads (3 formats) -> abilities ->
rank predictions -> residual logging -> all three reports.

Run:  python -m yks_institutional.demo
"""
from __future__ import annotations

import json

from .calibration.predict import (PlaceholderEngine, predict_and_log,
                                  residual_summary)
from .db import Database
from .reports.data import principal_dashboard, student_report, teacher_report
from .seed_synthetic import seed_database
from .stats.ability import estimate_abilities, refresh_school_abilities


def main():
    db = Database("demo_yks.sqlite3")
    print("=== Seeding synthetic school (200 students, 3 exams, 3 formats) ===")
    school, students, exam_ids = seed_database(db, seed=42, n_students=200)
    print(f"school={school.name}  exams={len(exam_ids)}")

    n = refresh_school_abilities(db, school.school_id)
    print(f"ability estimates written: {n}")

    print("\n=== Predictions (PLACEHOLDER engine — wire real engine before demo) ===")
    engine = PlaceholderEngine()
    cohort = [r for eid in exam_ids for r in db.results_for_exam(eid)]
    for st in students[:3]:
        mine = db.results_for_student(st.student_id)
        est = estimate_abilities(st.student_id, mine, cohort)
        pred = predict_and_log(db, student_id=st.student_id, estimates=est,
                               engine=engine, obp_raw=st.obp)
        print(f"no {st.school_student_no}: TYT net ~{pred.projected_tyt_net}, "
              f"rank {pred.rank_low:,} – {pred.rank_high:,} "
              f"(mid {pred.rank_mid:,}) flags={[f.value for f in pred.flags]}")

    print("\n=== Residual ledger ===")
    print(json.dumps(residual_summary(db), indent=2))

    print("\n=== Student report (first student) ===")
    print(json.dumps(student_report(db, students[0].student_id),
                     indent=2, ensure_ascii=False)[:900], "...")

    print("\n=== Teacher trends ===")
    tr = teacher_report(db, exam_ids)
    print(json.dumps(tr["trends"], indent=2, ensure_ascii=False))

    print("\n=== Principal dashboard ===")
    print(json.dumps(principal_dashboard(db, school.school_id, exam_ids),
                     indent=2, ensure_ascii=False))
    db.close()


if __name__ == "__main__":
    main()
