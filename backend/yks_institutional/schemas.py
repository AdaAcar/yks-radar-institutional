"""YKS Radar — Institutional backend schemas (CONTRACT v1.0).

This file is the single source of truth for data shapes. Any change here is a
contract change: bump CONTRACT_VERSION and share with all parties (frontend /
report work builds against these shapes).

Conventions (project-wide, do not violate):
  * Lower rank number = better, everywhere.
  * rank_margin = student_rank - threshold  (negative = student is competitive).
  * Warnings are never silent: every anomaly becomes a Warning surfaced upward.
  * IRT columns exist but are nullable — v1 fills classical stats only.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

CONTRACT_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Subject(str, Enum):
    # TYT
    TYT_TURKCE = "tyt_turkce"
    TYT_MATEMATIK = "tyt_matematik"
    TYT_SOSYAL = "tyt_sosyal"
    TYT_FEN = "tyt_fen"
    # AYT
    AYT_MATEMATIK = "ayt_matematik"
    AYT_FIZIK = "ayt_fizik"
    AYT_KIMYA = "ayt_kimya"
    AYT_BIYOLOJI = "ayt_biyoloji"
    AYT_EDEBIYAT = "ayt_edebiyat"
    AYT_TARIH1 = "ayt_tarih1"
    AYT_COGRAFYA1 = "ayt_cografya1"
    AYT_TARIH2 = "ayt_tarih2"
    AYT_COGRAFYA2 = "ayt_cografya2"
    AYT_FELSEFE = "ayt_felsefe"
    AYT_DIN = "ayt_din"

    @property
    def section(self) -> str:
        return "TYT" if self.value.startswith("tyt") else "AYT"


# Official question counts per subject (used for net projection and sanity checks)
SUBJECT_QUESTION_COUNTS: dict[Subject, int] = {
    Subject.TYT_TURKCE: 40,
    Subject.TYT_MATEMATIK: 40,
    Subject.TYT_SOSYAL: 20,
    Subject.TYT_FEN: 20,
    Subject.AYT_MATEMATIK: 40,
    Subject.AYT_FIZIK: 14,
    Subject.AYT_KIMYA: 13,
    Subject.AYT_BIYOLOJI: 13,
    Subject.AYT_EDEBIYAT: 24,
    Subject.AYT_TARIH1: 10,
    Subject.AYT_COGRAFYA1: 6,
    Subject.AYT_TARIH2: 11,
    Subject.AYT_COGRAFYA2: 11,
    Subject.AYT_FELSEFE: 12,
    Subject.AYT_DIN: 6,
}


class ScoreType(str, Enum):
    SAY = "SAY"
    EA = "EA"
    SOZ = "SOZ"
    DIL = "DIL"


class WarningSeverity(str, Enum):
    INFO = "info"          # noteworthy, no action needed
    WARNING = "warning"    # ingest proceeds, user should review
    ERROR = "error"        # row/record skipped, ingest of the rest proceeds
    FATAL = "fatal"        # whole upload rejected


class WarningCode(str, Enum):
    # Upload-level
    DUPLICATE_UPLOAD = "duplicate_upload"
    ANSWER_KEY_LENGTH_MISMATCH = "answer_key_length_mismatch"
    ANSWER_KEY_MISSING = "answer_key_missing"
    UNKNOWN_FORMAT = "unknown_answer_format"
    MIXED_FORMAT = "mixed_answer_format"
    # Student-level
    UNMATCHED_STUDENT = "unmatched_student"
    DUPLICATE_STUDENT_ROW = "duplicate_student_row"
    MISSING_STUDENT = "missing_student"           # registered but absent from upload
    EMPTY_RESPONSE_ROW = "empty_response_row"
    RESPONSE_LENGTH_MISMATCH = "response_length_mismatch"
    UNIFORM_ANSWERS = "uniform_answers"           # student answered same option everywhere
    # Distribution-level
    SUSPICIOUS_SCORE_DISTRIBUTION = "suspicious_score_distribution"
    ZERO_VARIANCE_QUESTION = "zero_variance_question"
    NEGATIVE_DISCRIMINATION = "negative_discrimination"
    # OBP handling (mirrors YKSRadar core engine behavior)
    OBP_AUTOCONVERTED = "obp_autoconverted_from_diploma_note"
    OBP_MISSING = "obp_missing_estimate_incomplete"


class IngestWarning(BaseModel):
    code: WarningCode
    severity: WarningSeverity
    message: str
    context: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return str(uuid.uuid4())


class School(BaseModel):
    school_id: str = Field(default_factory=_new_id)
    name: str
    city: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class Student(BaseModel):
    student_id: str = Field(default_factory=_new_id)   # internal UUID, anonymous
    school_id: str
    school_student_no: str                              # the school's own number, match key
    display_name: Optional[str] = None                  # optional, for fuzzy matching only
    graduation_year: Optional[int] = None
    consent: bool = False
    obp: Optional[float] = None                         # stored on 250–500 scale
    obp_flags: list[WarningCode] = Field(default_factory=list)

    @field_validator("school_student_no", mode="before")
    @classmethod
    def _norm_no(cls, v):
        return str(v).strip()


def normalize_obp(raw: Optional[float]) -> tuple[Optional[float], list[WarningCode]]:
    """Mirror of the core-engine OBP fix.

    * None/blank -> None + OBP_MISSING flag (contributes exactly zero downstream).
    * value <= 100 -> treated as diploma note, converted x5, floored at 250,
      flagged OBP_AUTOCONVERTED.
    * 250..500 -> accepted as-is.
    * anything else -> None + OBP_MISSING (never guess a phantom value).
    """
    if raw is None:
        return None, [WarningCode.OBP_MISSING]
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None, [WarningCode.OBP_MISSING]
    if v <= 0:
        return None, [WarningCode.OBP_MISSING]
    if v <= 100:
        return max(v * 5.0, 250.0), [WarningCode.OBP_AUTOCONVERTED]
    if 250.0 <= v <= 500.0:
        return v, []
    return None, [WarningCode.OBP_MISSING]


class Exam(BaseModel):
    exam_id: str = Field(default_factory=_new_id)
    school_id: str
    name: str
    exam_date: date
    publisher: Optional[str] = None
    section: str = "TYT"                                # "TYT" | "AYT" | "MIXED"
    content_hash: Optional[str] = None                  # duplicate detection
    created_at: datetime = Field(default_factory=lambda: datetime.now())


class Question(BaseModel):
    question_id: str = Field(default_factory=_new_id)
    exam_id: str
    position: int                                       # 1-based within exam
    subject: Subject
    topic: Optional[str] = None
    correct_answer: str                                 # canonical token, e.g. "A"
    option_count: int = 5
    # Classical test theory (filled by stats.classical on every ingest)
    p_value: Optional[float] = None                     # fraction correct
    point_biserial: Optional[float] = None
    n_responses: Optional[int] = None
    # IRT — reserved, nullable, v1 never writes these
    irt_difficulty: Optional[float] = None
    irt_discrimination: Optional[float] = None
    irt_guessing: Optional[float] = None        # 3PL-ready, v1 never writes


class Response(BaseModel):
    response_id: str = Field(default_factory=_new_id)
    student_id: str
    question_id: str
    exam_id: str
    given_answer: Optional[str] = None                  # canonical token; None = blank
    raw_answer: Optional[str] = None                    # as uploaded, audit trail
    is_correct: Optional[bool] = None                   # None when blank


class SubjectNet(BaseModel):
    subject: Subject
    correct: int
    wrong: int
    blank: int
    net: float                                          # correct - wrong/4

    @property
    def attempted(self) -> int:
        return self.correct + self.wrong

    @field_validator("net")
    @classmethod
    def _net_consistent(cls, v, info):
        # invalid states unrepresentable: net must equal correct - wrong/4
        c, w = info.data.get("correct"), info.data.get("wrong")
        if c is not None and w is not None and abs(v - (c - w / 4.0)) > 1e-9:
            raise ValueError("net must equal correct - wrong/4")
        return v


class ExamResult(BaseModel):
    result_id: str = Field(default_factory=_new_id)
    student_id: str
    exam_id: str
    nets: list[SubjectNet]
    total_net_tyt: float = 0.0
    total_net_ayt: float = 0.0
    warnings: list[IngestWarning] = Field(default_factory=list)


class AbilityEstimate(BaseModel):
    """Per-student, per-subject ability on a net-fraction scale in [-0.25, 1.0].

    theta = shrunk mean of (net / n_questions) across exams.
    v1 uses empirical-Bayes shrinkage toward the school cohort mean; the schema
    is stable so an IRT posterior can replace the estimator without migration.
    """
    estimate_id: str = Field(default_factory=_new_id)
    student_id: str
    subject: Subject
    as_of: date
    theta: float
    theta_se: float
    n_exams: int
    shrunk_from: float                                  # raw pre-shrinkage mean
    cohort_mean: float
    method: str = "shrunk_net_fraction_v1"


class RankPrediction(BaseModel):
    prediction_id: str = Field(default_factory=_new_id)
    student_id: str
    as_of: date
    score_type: str                                     # "SAY" | "EA" | ...
    projected_tyt_net: float
    projected_ayt_net: float
    obp_used: Optional[float]
    score_estimate: float
    rank_mid: int
    rank_low: int                                       # better boundary (smaller number)
    rank_high: int                                      # worse boundary
    flags: list[WarningCode] = Field(default_factory=list)
    engine: str = "institutional_hook_v1"

    @field_validator("rank_high")
    @classmethod
    def _rank_order(cls, v, info):
        # lower rank number = better; low <= mid <= high must hold
        lo, mid = info.data.get("rank_low"), info.data.get("rank_mid")
        if lo is not None and mid is not None and not (lo <= mid <= v):
            raise ValueError("rank interval must satisfy rank_low <= rank_mid <= rank_high")
        return v


class ResidualRecord(BaseModel):
    """The moat's training data. One row per prediction; outcome filled when
    official YKS results arrive. Never delete rows — supersede with new ones."""
    residual_id: str = Field(default_factory=_new_id)
    student_id: str
    prediction_id: str
    predicted_rank_mid: int
    predicted_rank_low: int
    predicted_rank_high: int
    predicted_at: date
    score_type: str
    # outcome — null until official results land
    actual_rank: Optional[int] = None
    outcome_source: Optional[str] = None                # "user_official_result" etc.
    outcome_recorded_at: Optional[date] = None
    sample_weight: float = 1.0                          # 4.0 for official results

    @property
    def residual(self) -> Optional[int]:
        if self.actual_rank is None:
            return None
        return self.actual_rank - self.predicted_rank_mid

    @property
    def covered(self) -> Optional[bool]:
        if self.actual_rank is None:
            return None
        return self.predicted_rank_low <= self.actual_rank <= self.predicted_rank_high
