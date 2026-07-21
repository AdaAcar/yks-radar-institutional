"""Ability estimation v1: shrunk net-fraction. Honest, simple, backtestable.

theta_raw  = mean over exams of (net / n_questions_in_subject_on_that_exam)
theta      = (n * theta_raw + K * cohort_mean) / (n + K)

where n = number of exams the student sat for that subject and K is the prior
strength (in "pseudo-exams"). K=1.5 default: a single mock moves a student most
of the way but keeps one-off flukes tempered; by 4-5 mocks the data dominates.

Rationale (mirrors the forecast_threshold lesson): with sparse per-student data,
an aggressive individual estimate is worse than a shrunk one — the same reason
trend-following hurt the closing-rank model. IRT replaces this estimator later
behind the same AbilityEstimate schema; nothing downstream changes.

SE: sample-based when n >= 2, binomial-approximation floor otherwise.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date

from ..schemas import (AbilityEstimate, ExamResult, Subject,
                       SUBJECT_QUESTION_COUNTS)

PRIOR_STRENGTH_K = 1.5
MIN_SE = 0.03          # never claim more precision than ~1 net in 33 questions
DEFAULT_SE = 0.12      # single-exam uncertainty on net-fraction scale


def _net_fractions_by_subject(
        results: list[ExamResult]) -> dict[Subject, list[float]]:
    out: dict[Subject, list[float]] = defaultdict(list)
    for res in results:
        for n in res.nets:
            total_q = n.correct + n.wrong + n.blank
            if total_q <= 0:
                continue
            out[n.subject].append(n.net / total_q)
    return out


def estimate_abilities(
        student_id: str,
        student_results: list[ExamResult],
        cohort_results: list[ExamResult],
        as_of: date | None = None,
        prior_strength: float = PRIOR_STRENGTH_K) -> list[AbilityEstimate]:
    """Estimate per-subject ability for one student, shrunk toward cohort."""
    as_of = as_of or date.today()
    mine = _net_fractions_by_subject(student_results)
    cohort = _net_fractions_by_subject(cohort_results)

    estimates: list[AbilityEstimate] = []
    for subject, fracs in mine.items():
        n = len(fracs)
        raw = statistics.mean(fracs)
        cohort_vals = cohort.get(subject, fracs)
        cohort_mean = statistics.mean(cohort_vals) if cohort_vals else raw
        theta = (n * raw + prior_strength * cohort_mean) / (n + prior_strength)
        if n >= 2:
            se = max(statistics.stdev(fracs) / math.sqrt(n), MIN_SE)
        else:
            se = DEFAULT_SE
        # shrinkage also shrinks SE slightly (borrowed strength), floor holds
        se = max(se * math.sqrt(n / (n + prior_strength)) + MIN_SE / 2, MIN_SE)
        estimates.append(AbilityEstimate(
            student_id=student_id, subject=subject, as_of=as_of,
            theta=theta, theta_se=se, n_exams=n,
            shrunk_from=raw, cohort_mean=cohort_mean))
    return estimates


def refresh_school_abilities(db, school_id: str,
                             as_of: date | None = None) -> int:
    """Recompute + persist ability estimates for every student in a school.
    Call after each accepted ingest. Returns number of estimates written."""
    as_of = as_of or date.today()
    students = db.students_for_school(school_id)
    cohort: list[ExamResult] = []
    per_student: dict[str, list[ExamResult]] = {}
    for st in students:
        res = db.results_for_student(st.student_id)
        per_student[st.student_id] = res
        cohort.extend(res)
    written = 0
    for sid, res in per_student.items():
        if not res:
            continue
        for est in estimate_abilities(sid, res, cohort, as_of=as_of):
            db.add_ability(est)
            written += 1
    return written


def project_nets(estimates: list[AbilityEstimate]) -> dict[str, float]:
    """Project ability -> expected official-exam nets.

    Returns {"tyt_net": x, "ayt_net": y, "tyt_net_low/high", "ayt_net_low/high"}
    using official subject question counts. Subjects the student never sat
    contribute zero (surfaced upstream as an incompleteness flag).
    """
    tyt = ayt = 0.0
    tyt_var = ayt_var = 0.0
    for est in estimates:
        n_q = SUBJECT_QUESTION_COUNTS[est.subject]
        mean = est.theta * n_q
        var = (est.theta_se * n_q) ** 2
        if est.subject.section == "TYT":
            tyt += mean
            tyt_var += var
        else:
            ayt += mean
            ayt_var += var
    z = 1.28  # ~80% interval; calibration data will retune this
    return {
        "tyt_net": tyt, "ayt_net": ayt,
        "tyt_net_low": max(tyt - z * math.sqrt(tyt_var), -30.0),
        "tyt_net_high": min(tyt + z * math.sqrt(tyt_var), 120.0),
        "ayt_net_low": max(ayt - z * math.sqrt(ayt_var), -20.0),
        "ayt_net_high": min(ayt + z * math.sqrt(ayt_var), 80.0),
    }
