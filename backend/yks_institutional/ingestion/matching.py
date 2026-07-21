"""Matching engine: school student number -> internal Student UUID.

Strategy (in order):
  1. Exact match on normalized school_student_no.
  2. Zero-padding tolerant match ("0042" == "42").
  3. Fuzzy name fallback (only if the upload row carries a name AND exactly one
     registered student clears the similarity threshold — ambiguity never guesses).

Every unmatched row is a surfaced warning, never silently dropped.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from ..schemas import IngestWarning, Student, WarningCode, WarningSeverity
from .adapters import StudentRow

NAME_SIMILARITY_THRESHOLD = 0.88


def _norm_no(no: str) -> str:
    return str(no).strip().lstrip("0") or "0"


def _norm_name(name: str) -> str:
    # Turkish-aware casefold: İ->i, I->ı handled via lower with replacements
    s = name.strip().replace("İ", "i").replace("I", "ı").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.split())


@dataclass
class MatchResult:
    matched: dict[str, Student] = field(default_factory=dict)     # student_no -> Student
    unmatched: list[StudentRow] = field(default_factory=list)
    missing_students: list[Student] = field(default_factory=list) # registered, absent
    duplicate_rows: list[StudentRow] = field(default_factory=list)
    warnings: list[IngestWarning] = field(default_factory=list)


def match_rows(rows: list[StudentRow], registered: list[Student]) -> MatchResult:
    res = MatchResult()
    by_no: dict[str, Student] = {}
    for st in registered:
        by_no[_norm_no(st.school_student_no)] = st

    seen_upload_nos: set[str] = set()
    matched_ids: set[str] = set()

    for row in rows:
        key = _norm_no(row.student_no)
        if key in seen_upload_nos:
            res.duplicate_rows.append(row)
            res.warnings.append(IngestWarning(
                code=WarningCode.DUPLICATE_STUDENT_ROW,
                severity=WarningSeverity.WARNING,
                message=f"Student no {row.student_no} appears more than once; "
                        f"first occurrence kept, row {row.source_row} ignored",
                context={"student_no": row.student_no, "row": row.source_row}))
            continue
        seen_upload_nos.add(key)

        st = by_no.get(key)
        if st is None and row.name:
            st = _fuzzy_by_name(row.name, registered, matched_ids)
            if st is not None:
                res.warnings.append(IngestWarning(
                    code=WarningCode.UNMATCHED_STUDENT,
                    severity=WarningSeverity.INFO,
                    message=f"Student no {row.student_no} not registered; matched "
                            f"by name to registered student "
                            f"no {st.school_student_no}",
                    context={"upload_no": row.student_no,
                             "matched_no": st.school_student_no}))
        if st is None:
            res.unmatched.append(row)
            res.warnings.append(IngestWarning(
                code=WarningCode.UNMATCHED_STUDENT,
                severity=WarningSeverity.ERROR,
                message=f"Row {row.source_row}: student no {row.student_no} not "
                        f"found in school roster; responses NOT imported",
                context={"student_no": row.student_no, "row": row.source_row}))
            continue
        res.matched[row.student_no] = st
        matched_ids.add(st.student_id)

    for st in registered:
        if st.student_id not in matched_ids:
            res.missing_students.append(st)
    if res.missing_students:
        res.warnings.append(IngestWarning(
            code=WarningCode.MISSING_STUDENT,
            severity=WarningSeverity.WARNING,
            message=f"{len(res.missing_students)} registered student(s) absent "
                    f"from this upload",
            context={"student_nos": [s.school_student_no
                                     for s in res.missing_students][:50]}))
    return res


def _fuzzy_by_name(name: str, registered: list[Student],
                   already_matched: set[str]) -> Optional[Student]:
    target = _norm_name(name)
    hits: list[Student] = []
    for st in registered:
        if st.student_id in already_matched or not st.display_name:
            continue
        score = SequenceMatcher(None, target, _norm_name(st.display_name)).ratio()
        if score >= NAME_SIMILARITY_THRESHOLD:
            hits.append(st)
    return hits[0] if len(hits) == 1 else None
