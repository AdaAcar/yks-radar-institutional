"""SQLite persistence layer. Zero-ops v1 store; schema mirrors schemas.py.

Postgres migration later is a mechanical change — all SQL here is standard.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from .schemas import (
    AbilityEstimate, Exam, ExamResult, Question, RankPrediction,
    ResidualRecord, Response, School, Student, Subject, SubjectNet,
    IngestWarning, WarningCode,
)

DDL = """
CREATE TABLE IF NOT EXISTS schools (
    school_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    school_id TEXT NOT NULL REFERENCES schools(school_id),
    school_student_no TEXT NOT NULL,
    display_name TEXT,
    graduation_year INTEGER,
    consent INTEGER NOT NULL DEFAULT 0,
    obp REAL,
    obp_flags TEXT NOT NULL DEFAULT '[]',
    UNIQUE(school_id, school_student_no)
);
CREATE TABLE IF NOT EXISTS exams (
    exam_id TEXT PRIMARY KEY,
    school_id TEXT NOT NULL REFERENCES schools(school_id),
    name TEXT NOT NULL,
    exam_date TEXT NOT NULL,
    publisher TEXT,
    section TEXT NOT NULL,
    content_hash TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exams_hash ON exams(school_id, content_hash);
CREATE TABLE IF NOT EXISTS questions (
    question_id TEXT PRIMARY KEY,
    exam_id TEXT NOT NULL REFERENCES exams(exam_id),
    position INTEGER NOT NULL,
    subject TEXT NOT NULL,
    topic TEXT,
    correct_answer TEXT NOT NULL,
    option_count INTEGER NOT NULL DEFAULT 5,
    p_value REAL,
    point_biserial REAL,
    n_responses INTEGER,
    irt_difficulty REAL,
    irt_discrimination REAL,
    irt_guessing REAL,
    UNIQUE(exam_id, position)
);
CREATE TABLE IF NOT EXISTS responses (
    response_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(student_id),
    question_id TEXT NOT NULL REFERENCES questions(question_id),
    exam_id TEXT NOT NULL REFERENCES exams(exam_id),
    given_answer TEXT,
    raw_answer TEXT,
    is_correct INTEGER,
    UNIQUE(student_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_responses_exam ON responses(exam_id);
CREATE INDEX IF NOT EXISTS idx_responses_student ON responses(student_id);
CREATE TABLE IF NOT EXISTS exam_results (
    result_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    exam_id TEXT NOT NULL,
    nets TEXT NOT NULL,               -- JSON list[SubjectNet]
    total_net_tyt REAL NOT NULL,
    total_net_ayt REAL NOT NULL,
    warnings TEXT NOT NULL DEFAULT '[]',
    UNIQUE(student_id, exam_id)
);
CREATE TABLE IF NOT EXISTS ability_estimates (
    estimate_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    as_of TEXT NOT NULL,
    theta REAL NOT NULL,
    theta_se REAL NOT NULL,
    n_exams INTEGER NOT NULL,
    shrunk_from REAL NOT NULL,
    cohort_mean REAL NOT NULL,
    method TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ability_student ON ability_estimates(student_id, subject, as_of);
CREATE TABLE IF NOT EXISTS rank_predictions (
    prediction_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    score_type TEXT NOT NULL,
    projected_tyt_net REAL NOT NULL,
    projected_ayt_net REAL NOT NULL,
    obp_used REAL,
    score_estimate REAL NOT NULL,
    rank_mid INTEGER NOT NULL,
    rank_low INTEGER NOT NULL,
    rank_high INTEGER NOT NULL,
    flags TEXT NOT NULL DEFAULT '[]',
    engine TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS residuals (
    residual_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    prediction_id TEXT NOT NULL,
    predicted_rank_mid INTEGER NOT NULL,
    predicted_rank_low INTEGER NOT NULL,
    predicted_rank_high INTEGER NOT NULL,
    predicted_at TEXT NOT NULL,
    score_type TEXT NOT NULL,
    actual_rank INTEGER,
    outcome_source TEXT,
    outcome_recorded_at TEXT,
    sample_weight REAL NOT NULL DEFAULT 1.0
);
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS upload_log (
    upload_id TEXT PRIMARY KEY,
    school_id TEXT NOT NULL,
    exam_id TEXT,
    filename TEXT,
    content_hash TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    status TEXT NOT NULL,             -- accepted | rejected
    warnings TEXT NOT NULL DEFAULT '[]'
);
"""


class Database:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(DDL)
        if self._conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 0:
            self._conn.execute("INSERT INTO schema_version VALUES (1)")
            self._conn.commit()

    def close(self):
        self._conn.close()

    @contextmanager
    def tx(self):
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # ---- schools / students -------------------------------------------------
    def add_school(self, s: School):
        with self.tx() as c:
            c.execute(
                "INSERT INTO schools VALUES (?,?,?,?)",
                (s.school_id, s.name, s.city, s.created_at.isoformat()),
            )

    def add_student(self, st: Student):
        with self.tx() as c:
            c.execute(
                "INSERT INTO students VALUES (?,?,?,?,?,?,?,?)",
                (st.student_id, st.school_id, st.school_student_no,
                 st.display_name, st.graduation_year, int(st.consent),
                 st.obp, json.dumps([f.value for f in st.obp_flags])),
            )

    def students_for_school(self, school_id: str) -> list[Student]:
        rows = self._conn.execute(
            "SELECT * FROM students WHERE school_id=?", (school_id,)
        ).fetchall()
        return [self._row_to_student(r) for r in rows]

    @staticmethod
    def _row_to_student(r) -> Student:
        return Student(
            student_id=r["student_id"], school_id=r["school_id"],
            school_student_no=r["school_student_no"], display_name=r["display_name"],
            graduation_year=r["graduation_year"], consent=bool(r["consent"]),
            obp=r["obp"],
            obp_flags=[WarningCode(x) for x in json.loads(r["obp_flags"])],
        )

    # ---- exams / questions / responses -------------------------------------
    def add_exam(self, e: Exam):
        with self.tx() as c:
            c.execute(
                "INSERT INTO exams VALUES (?,?,?,?,?,?,?,?)",
                (e.exam_id, e.school_id, e.name, e.exam_date.isoformat(),
                 e.publisher, e.section, e.content_hash, e.created_at.isoformat()),
            )

    def exam_hash_exists(self, school_id: str, content_hash: str) -> bool:
        r = self._conn.execute(
            "SELECT 1 FROM exams WHERE school_id=? AND content_hash=?",
            (school_id, content_hash),
        ).fetchone()
        return r is not None

    def add_questions(self, qs: Iterable[Question]):
        with self.tx() as c:
            c.executemany(
                "INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(q.question_id, q.exam_id, q.position, q.subject.value, q.topic,
                  q.correct_answer, q.option_count, q.p_value, q.point_biserial,
                  q.n_responses, q.irt_difficulty, q.irt_discrimination,
                  q.irt_guessing) for q in qs],
            )

    def questions_for_exam(self, exam_id: str) -> list[Question]:
        rows = self._conn.execute(
            "SELECT * FROM questions WHERE exam_id=? ORDER BY position", (exam_id,)
        ).fetchall()
        return [Question(
            question_id=r["question_id"], exam_id=r["exam_id"], position=r["position"],
            subject=Subject(r["subject"]), topic=r["topic"],
            correct_answer=r["correct_answer"], option_count=r["option_count"],
            p_value=r["p_value"], point_biserial=r["point_biserial"],
            n_responses=r["n_responses"], irt_difficulty=r["irt_difficulty"],
            irt_discrimination=r["irt_discrimination"],
            irt_guessing=r["irt_guessing"],
        ) for r in rows]

    def update_question_stats(self, question_id: str, p_value: float,
                              point_biserial: Optional[float], n_responses: int):
        with self.tx() as c:
            c.execute(
                "UPDATE questions SET p_value=?, point_biserial=?, n_responses=? "
                "WHERE question_id=?",
                (p_value, point_biserial, n_responses, question_id),
            )

    def add_responses(self, rs: Iterable[Response]):
        with self.tx() as c:
            c.executemany(
                "INSERT INTO responses VALUES (?,?,?,?,?,?,?)",
                [(r.response_id, r.student_id, r.question_id, r.exam_id,
                  r.given_answer, r.raw_answer,
                  None if r.is_correct is None else int(r.is_correct)) for r in rs],
            )

    def responses_for_exam(self, exam_id: str) -> list[Response]:
        rows = self._conn.execute(
            "SELECT * FROM responses WHERE exam_id=?", (exam_id,)
        ).fetchall()
        return [Response(
            response_id=r["response_id"], student_id=r["student_id"],
            question_id=r["question_id"], exam_id=r["exam_id"],
            given_answer=r["given_answer"], raw_answer=r["raw_answer"],
            is_correct=None if r["is_correct"] is None else bool(r["is_correct"]),
        ) for r in rows]

    # ---- results / abilities / predictions / residuals ----------------------
    def add_exam_result(self, res: ExamResult):
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO exam_results VALUES (?,?,?,?,?,?,?)",
                (res.result_id, res.student_id, res.exam_id,
                 json.dumps([n.model_dump(mode="json") for n in res.nets]),
                 res.total_net_tyt, res.total_net_ayt,
                 json.dumps([w.model_dump(mode="json") for w in res.warnings])),
            )

    def results_for_student(self, student_id: str) -> list[ExamResult]:
        rows = self._conn.execute(
            "SELECT * FROM exam_results WHERE student_id=?", (student_id,)
        ).fetchall()
        return [self._row_to_result(r) for r in rows]

    def results_for_exam(self, exam_id: str) -> list[ExamResult]:
        rows = self._conn.execute(
            "SELECT * FROM exam_results WHERE exam_id=?", (exam_id,)
        ).fetchall()
        return [self._row_to_result(r) for r in rows]

    @staticmethod
    def _row_to_result(r) -> ExamResult:
        return ExamResult(
            result_id=r["result_id"], student_id=r["student_id"], exam_id=r["exam_id"],
            nets=[SubjectNet(**n) for n in json.loads(r["nets"])],
            total_net_tyt=r["total_net_tyt"], total_net_ayt=r["total_net_ayt"],
            warnings=[IngestWarning(**w) for w in json.loads(r["warnings"])],
        )

    def add_ability(self, a: AbilityEstimate):
        with self.tx() as c:
            c.execute(
                "INSERT INTO ability_estimates VALUES (?,?,?,?,?,?,?,?,?,?)",
                (a.estimate_id, a.student_id, a.subject.value, a.as_of.isoformat(),
                 a.theta, a.theta_se, a.n_exams, a.shrunk_from, a.cohort_mean, a.method),
            )

    def latest_abilities(self, student_id: str) -> list[AbilityEstimate]:
        rows = self._conn.execute(
            """SELECT a.* FROM ability_estimates a
               JOIN (SELECT subject, MAX(as_of) m FROM ability_estimates
                     WHERE student_id=? GROUP BY subject) b
               ON a.subject=b.subject AND a.as_of=b.m
               WHERE a.student_id=?""",
            (student_id, student_id),
        ).fetchall()
        return [AbilityEstimate(
            estimate_id=r["estimate_id"], student_id=r["student_id"],
            subject=Subject(r["subject"]), as_of=date.fromisoformat(r["as_of"]),
            theta=r["theta"], theta_se=r["theta_se"], n_exams=r["n_exams"],
            shrunk_from=r["shrunk_from"], cohort_mean=r["cohort_mean"],
            method=r["method"],
        ) for r in rows]

    def add_prediction(self, p: RankPrediction):
        with self.tx() as c:
            c.execute(
                "INSERT INTO rank_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.prediction_id, p.student_id, p.as_of.isoformat(), p.score_type,
                 p.projected_tyt_net, p.projected_ayt_net, p.obp_used,
                 p.score_estimate, p.rank_mid, p.rank_low, p.rank_high,
                 json.dumps([f.value for f in p.flags]), p.engine),
            )

    def add_residual(self, r: ResidualRecord):
        with self.tx() as c:
            c.execute(
                "INSERT INTO residuals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (r.residual_id, r.student_id, r.prediction_id,
                 r.predicted_rank_mid, r.predicted_rank_low, r.predicted_rank_high,
                 r.predicted_at.isoformat(), r.score_type, r.actual_rank,
                 r.outcome_source,
                 r.outcome_recorded_at.isoformat() if r.outcome_recorded_at else None,
                 r.sample_weight),
            )

    def record_outcome(self, student_id: str, actual_rank: int,
                       source: str = "user_official_result",
                       score_type: Optional[str] = None,
                       sample_weight: Optional[float] = None) -> int:
        """Fill outcome on all open residuals for a student. Returns rows updated.
        Official results weigh 4x by default (core calibration convention)."""
        if sample_weight is None:
            sample_weight = 4.0 if source == "user_official_result" else 1.0
        if sample_weight <= 0:
            raise ValueError("sample_weight must be positive")
        with self.tx() as c:
            q = ("UPDATE residuals SET actual_rank=?, outcome_source=?, "
                 "outcome_recorded_at=?, sample_weight=? "
                 "WHERE student_id=? AND actual_rank IS NULL")
            params: list = [actual_rank, source, date.today().isoformat(),
                            sample_weight, student_id]
            if score_type:
                q += " AND score_type=?"
                params.append(score_type)
            cur = c.execute(q, params)
            return cur.rowcount

    def open_residuals(self) -> list[ResidualRecord]:
        rows = self._conn.execute(
            "SELECT * FROM residuals WHERE actual_rank IS NULL").fetchall()
        return [self._row_to_residual(r) for r in rows]

    def closed_residuals(self) -> list[ResidualRecord]:
        rows = self._conn.execute(
            "SELECT * FROM residuals WHERE actual_rank IS NOT NULL").fetchall()
        return [self._row_to_residual(r) for r in rows]

    @staticmethod
    def _row_to_residual(r) -> ResidualRecord:
        return ResidualRecord(
            residual_id=r["residual_id"], student_id=r["student_id"],
            prediction_id=r["prediction_id"],
            predicted_rank_mid=r["predicted_rank_mid"],
            predicted_rank_low=r["predicted_rank_low"],
            predicted_rank_high=r["predicted_rank_high"],
            predicted_at=date.fromisoformat(r["predicted_at"]),
            score_type=r["score_type"], actual_rank=r["actual_rank"],
            outcome_source=r["outcome_source"],
            outcome_recorded_at=(date.fromisoformat(r["outcome_recorded_at"])
                                 if r["outcome_recorded_at"] else None),
            sample_weight=r["sample_weight"],
        )

    def log_upload(self, upload_id: str, school_id: str, exam_id: Optional[str],
                   filename: Optional[str], content_hash: str, status: str,
                   warnings: list[IngestWarning]):
        with self.tx() as c:
            c.execute(
                "INSERT INTO upload_log VALUES (?,?,?,?,?,?,?,?)",
                (upload_id, school_id, exam_id, filename, content_hash,
                 datetime.now().isoformat(), status,
                 json.dumps([w.model_dump(mode="json") for w in warnings])),
            )
