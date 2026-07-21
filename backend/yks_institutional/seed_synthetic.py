"""Synthetic school generator: 200 students, 3 TYT mocks, ability-driven
responses. Purpose: everything downstream is testable before real data lands.

Generative model (deliberately simple):
  student ability u ~ Normal(0.45, 0.15) clipped to [0.05, 0.95]
  question difficulty d_q ~ Uniform(0.15, 0.85)
  P(correct) = sigmoid(6 * (u - d_q) )  -> produces sane p-values & positive rpb
  P(blank)   = 0.06 flat
  wrong answers uniform over remaining options

Also emits raw upload files (CSV letters, CSV digits, XLSX) so the adapter
layer gets exercised the same way real files will.
"""
from __future__ import annotations

import io
import math
import random
from datetime import date

from .schemas import School, Student, Subject, normalize_obp

TYT_BLOCKS = [(Subject.TYT_TURKCE, 1, 40), (Subject.TYT_SOSYAL, 41, 60),
              (Subject.TYT_MATEMATIK, 61, 100), (Subject.TYT_FEN, 101, 120)]
OPTIONS = "ABCDE"


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def make_school(rng: random.Random, n_students: int = 200):
    school = School(name="Sentetik Anadolu Lisesi", city="Istanbul")
    students, abilities = [], {}
    for i in range(n_students):
        u = min(max(rng.gauss(0.45, 0.15), 0.05), 0.95)
        raw_obp = rng.choice([rng.uniform(60, 100),      # diploma note style
                              rng.uniform(300, 500),     # true OBP style
                              None])                     # missing
        obp, flags = normalize_obp(raw_obp)
        st = Student(school_id=school.school_id,
                     school_student_no=str(1000 + i),
                     display_name=f"Ogrenci {1000 + i}",
                     graduation_year=2026, consent=True,
                     obp=obp, obp_flags=flags)
        students.append(st)
        abilities[st.school_student_no] = u
    return school, students, abilities


def make_exam_data(rng: random.Random, abilities: dict[str, float],
                   n_questions: int = 120,
                   ability_shift: float = 0.0):
    """Returns (answer_key, {student_no: [answer|None]*n_questions})."""
    key = [rng.choice(OPTIONS) for _ in range(n_questions)]
    difficulty = [rng.uniform(0.15, 0.85) for _ in range(n_questions)]
    sheets = {}
    for no, u in abilities.items():
        u_eff = min(max(u + ability_shift + rng.gauss(0, 0.03), 0.02), 0.98)
        row = []
        for qi in range(n_questions):
            if rng.random() < 0.06:
                row.append(None)
                continue
            p = _sigmoid(6.0 * (u_eff - difficulty[qi]))
            if rng.random() < p:
                row.append(key[qi])
            else:
                row.append(rng.choice([o for o in OPTIONS if o != key[qi]]))
        sheets[no] = row
    return key, sheets


# ---------------------------------------------------------------------------
# Raw file emitters — exercise the adapters exactly like real uploads
# ---------------------------------------------------------------------------

def to_csv_letters(key, sheets) -> bytes:
    lines = ["Ogrenci No;" + ";".join(f"S{i+1}" for i in range(len(key)))]
    lines.append("CEVAP ANAHTARI;" + ";".join(key))
    for no, row in sheets.items():
        lines.append(no + ";" + ";".join(a if a else "" for a in row))
    return ("\n".join(lines)).encode("utf-8")


def to_csv_digits(key, sheets) -> bytes:
    inv = {c: str(i + 1) for i, c in enumerate(OPTIONS)}
    lines = ["No," + ",".join(f"Q{i+1}" for i in range(len(key)))]
    lines.append("KEY," + ",".join(inv[k] for k in key))
    for no, row in sheets.items():
        lines.append(no + "," + ",".join(inv[a] if a else "-" for a in row))
    return ("\n".join(lines)).encode("utf-8")


def to_xlsx(key, sheets) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Öğrenci No"] + [f"S{i+1}" for i in range(len(key))])
    ws.append(["Cevap Anahtarı"] + list(key))
    for no, row in sheets.items():
        ws.append([int(no)] + [a if a else None for a in row])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def seed_database(db, seed: int = 42, n_students: int = 200):
    """Full end-to-end seed: school + students + 3 exams ingested from raw
    files in three different formats. Returns (school, students, exam_ids)."""
    from .ingestion.pipeline import SubjectBlock, ingest_upload

    rng = random.Random(seed)
    school, students, abilities = make_school(rng, n_students)
    db.add_school(school)
    for st in students:
        db.add_student(st)

    blocks = [SubjectBlock(subject=s, start=a, end=b) for s, a, b in TYT_BLOCKS]
    exam_ids = []
    specs = [
        ("Eylül TYT Denemesi", date(2025, 9, 20), 0.00, to_csv_letters, "eylul.csv"),
        ("Kasım TYT Denemesi", date(2025, 11, 15), 0.03, to_csv_digits, "kasim.csv"),
        ("Ocak TYT Denemesi", date(2026, 1, 17), 0.06, to_xlsx, "ocak.xlsx"),
    ]
    for name, dt, shift, emit, fname in specs:
        key, sheets = make_exam_data(rng, abilities, 120, shift)
        outcome = ingest_upload(
            db, school_id=school.school_id, file_bytes=emit(key, sheets),
            filename=fname, exam_name=name, exam_date=dt,
            subject_blocks=blocks)
        assert outcome.accepted, [w.message for w in outcome.warnings]
        exam_ids.append(outcome.exam_id)
    return school, students, exam_ids
