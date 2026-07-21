"""End-to-end ingestion: file bytes -> parsed -> matched -> validated ->
persisted (exam, questions, responses, per-student results) -> item stats.

Returns an IngestOutcome carrying every warning generated at every stage.
Nothing fails silently; FATAL warnings reject the upload atomically.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from ..db import Database
from ..schemas import (Exam, ExamResult, IngestWarning, Question, Response,
                       Subject, SubjectNet, WarningCode, WarningSeverity)
from ..stats.classical import compute_item_stats
from .long_format import parse_upload_any
from .matching import match_rows
from .validation import ValidationReport, content_hash, validate_batch


@dataclass
class SubjectBlock:
    """Maps a contiguous span of question positions to a subject.
    Example TYT: [(TYT_TURKCE, 1, 40), (TYT_SOSYAL, 41, 60), ...]"""
    subject: Subject
    start: int   # 1-based inclusive
    end: int     # inclusive


@dataclass
class IngestOutcome:
    accepted: bool
    exam_id: str | None
    n_students_imported: int
    n_students_unmatched: int
    n_registered_missing: int
    warnings: list[IngestWarning] = field(default_factory=list)

    @property
    def fatal(self) -> bool:
        return any(w.severity == WarningSeverity.FATAL for w in self.warnings)


def ingest_upload(db: Database, *, school_id: str, file_bytes: bytes,
                  filename: str, exam_name: str, exam_date: date,
                  subject_blocks: list[SubjectBlock],
                  answer_key: list[str] | None = None,
                  publisher: str | None = None,
                  topics: dict[int, str] | None = None) -> IngestOutcome:
    upload_id = str(uuid.uuid4())
    h = content_hash(file_bytes)
    topics = topics or {}

    batch = parse_upload_any(file_bytes, filename)
    dup = db.exam_hash_exists(school_id, h)
    report: ValidationReport = validate_batch(batch, answer_key, dup)

    key = answer_key or batch.answer_key

    # subject blocks must cover exactly the question span
    if not report.fatal:
        covered = sorted(p for b in subject_blocks for p in range(b.start, b.end + 1))
        if covered != list(range(1, batch.n_questions + 1)):
            report.add(IngestWarning(
                code=WarningCode.ANSWER_KEY_LENGTH_MISMATCH,
                severity=WarningSeverity.FATAL,
                message=f"Subject blocks cover {len(covered)} positions but exam "
                        f"has {batch.n_questions} questions",
                context={"covered": len(covered), "n_questions": batch.n_questions}))

    if report.fatal:
        db.log_upload(upload_id, school_id, None, filename, h, "rejected",
                      report.warnings)
        return IngestOutcome(accepted=False, exam_id=None, n_students_imported=0,
                             n_students_unmatched=0, n_registered_missing=0,
                             warnings=report.warnings)

    registered = db.students_for_school(school_id)
    match = match_rows(batch.rows, registered)
    all_warnings = report.warnings + match.warnings

    section = _infer_section(subject_blocks)
    exam = Exam(school_id=school_id, name=exam_name, exam_date=exam_date,
                publisher=publisher, section=section, content_hash=h)
    db.add_exam(exam)

    pos_to_subject = {}
    for b in subject_blocks:
        for p in range(b.start, b.end + 1):
            pos_to_subject[p] = b.subject
    questions = [Question(exam_id=exam.exam_id, position=p,
                          subject=pos_to_subject[p], topic=topics.get(p),
                          correct_answer=key[p - 1],
                          option_count=batch.option_count)
                 for p in range(1, batch.n_questions + 1)]
    db.add_questions(questions)
    q_by_pos = {q.position: q for q in questions}

    responses: list[Response] = []
    score_matrix: list[list[int]] = []
    imported = 0
    for row in batch.rows:
        st = match.matched.get(row.student_no)
        if st is None or len(row.answers) != batch.n_questions:
            continue
        row_scores: list[int] = []
        subject_tally: dict[Subject, dict[str, int]] = {}
        for p in range(1, batch.n_questions + 1):
            given = row.answers[p - 1]
            correct = None if given is None else (given == key[p - 1])
            responses.append(Response(
                student_id=st.student_id, question_id=q_by_pos[p].question_id,
                exam_id=exam.exam_id, given_answer=given, is_correct=correct))
            row_scores.append(1 if correct else 0)
            subj = pos_to_subject[p]
            t = subject_tally.setdefault(subj, {"c": 0, "w": 0, "b": 0})
            if given is None:
                t["b"] += 1
            elif correct:
                t["c"] += 1
            else:
                t["w"] += 1
        score_matrix.append(row_scores)

        nets = [SubjectNet(subject=s, correct=t["c"], wrong=t["w"], blank=t["b"],
                           net=t["c"] - t["w"] / 4.0)
                for s, t in subject_tally.items()]
        result = ExamResult(
            student_id=st.student_id, exam_id=exam.exam_id, nets=nets,
            total_net_tyt=sum(n.net for n in nets if n.subject.section == "TYT"),
            total_net_ayt=sum(n.net for n in nets if n.subject.section == "AYT"))
        db.add_exam_result(result)
        imported += 1

    db.add_responses(responses)

    # knowledge layer v0: classical stats on every ingest
    if score_matrix:
        for item in compute_item_stats(score_matrix):
            q = q_by_pos[item.position]
            db.update_question_stats(q.question_id, item.p_value,
                                     item.point_biserial, item.n)
            if item.p_value in (0.0, 1.0):
                all_warnings.append(IngestWarning(
                    code=WarningCode.ZERO_VARIANCE_QUESTION,
                    severity=WarningSeverity.INFO,
                    message=f"Q{item.position}: everyone "
                            f"{'correct' if item.p_value == 1.0 else 'wrong'} — "
                            f"no discrimination information",
                    context={"position": item.position}))
            elif item.point_biserial is not None and item.point_biserial < -0.05:
                all_warnings.append(IngestWarning(
                    code=WarningCode.NEGATIVE_DISCRIMINATION,
                    severity=WarningSeverity.WARNING,
                    message=f"Q{item.position}: negative discrimination "
                            f"({item.point_biserial:.2f}) — stronger students "
                            f"miss it more; check the answer key for this item",
                    context={"position": item.position,
                             "rpb": round(item.point_biserial, 3)}))

    db.log_upload(upload_id, school_id, exam.exam_id, filename, h, "accepted",
                  all_warnings)
    return IngestOutcome(
        accepted=True, exam_id=exam.exam_id, n_students_imported=imported,
        n_students_unmatched=len(match.unmatched),
        n_registered_missing=len(match.missing_students),
        warnings=all_warnings)


def _infer_section(blocks: list[SubjectBlock]) -> str:
    secs = {b.subject.section for b in blocks}
    return secs.pop() if len(secs) == 1 else "MIXED"
