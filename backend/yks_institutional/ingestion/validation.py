"""Upload validation. Everything returns warnings; nothing fails silently.

Checks:
  * duplicate upload (content hash vs. upload log / existing exams)
  * answer key present & length matches question count
  * per-row response length vs. question count
  * fully blank rows
  * uniform-answer rows (same option everywhere -> likely optic misread)
  * suspicious score distribution (mean too high/low, zero variance)
"""
from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass, field

from ..schemas import IngestWarning, WarningCode, WarningSeverity
from .adapters import UploadBatch


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class ValidationReport:
    warnings: list[IngestWarning] = field(default_factory=list)
    fatal: bool = False

    def add(self, w: IngestWarning):
        self.warnings.append(w)
        if w.severity == WarningSeverity.FATAL:
            self.fatal = True


def validate_batch(batch: UploadBatch,
                   answer_key: list[str] | None,
                   is_duplicate_upload: bool) -> ValidationReport:
    rep = ValidationReport()
    for w in batch.warnings:
        rep.add(w)

    if is_duplicate_upload:
        rep.add(IngestWarning(
            code=WarningCode.DUPLICATE_UPLOAD, severity=WarningSeverity.FATAL,
            message="This exact file was already uploaded for this school; "
                    "upload rejected to prevent double-counting",
            context={}))
        return rep

    key = answer_key or batch.answer_key
    if key is None:
        rep.add(IngestWarning(
            code=WarningCode.ANSWER_KEY_MISSING, severity=WarningSeverity.FATAL,
            message="No answer key: not embedded in file and none supplied",
            context={}))
        return rep
    if len(key) != batch.n_questions:
        rep.add(IngestWarning(
            code=WarningCode.ANSWER_KEY_LENGTH_MISMATCH,
            severity=WarningSeverity.FATAL,
            message=f"Answer key has {len(key)} entries but file has "
                    f"{batch.n_questions} answer columns",
            context={"key_len": len(key), "n_questions": batch.n_questions}))
        return rep

    scores = []
    for row in batch.rows:
        n_ans = len(row.answers)
        if n_ans != batch.n_questions:
            rep.add(IngestWarning(
                code=WarningCode.RESPONSE_LENGTH_MISMATCH,
                severity=WarningSeverity.ERROR,
                message=f"Row {row.source_row} (no {row.student_no}): "
                        f"{n_ans} answers vs {batch.n_questions} questions",
                context={"student_no": row.student_no}))
            continue
        non_blank = [a for a in row.answers if a is not None]
        if not non_blank:
            rep.add(IngestWarning(
                code=WarningCode.EMPTY_RESPONSE_ROW,
                severity=WarningSeverity.WARNING,
                message=f"Student no {row.student_no}: entire row blank "
                        f"(absent or optic read failure?)",
                context={"student_no": row.student_no}))
        elif len(set(non_blank)) == 1 and len(non_blank) >= max(10, batch.n_questions // 2):
            rep.add(IngestWarning(
                code=WarningCode.UNIFORM_ANSWERS,
                severity=WarningSeverity.WARNING,
                message=f"Student no {row.student_no}: answered "
                        f"'{non_blank[0]}' on every question — verify optic read",
                context={"student_no": row.student_no}))
        scores.append(sum(1 for a, k in zip(row.answers, key) if a == k))

    if len(scores) >= 5:
        mean_frac = statistics.mean(scores) / max(batch.n_questions, 1)
        stdev = statistics.pstdev(scores)
        chance = 1.0 / batch.option_count
        if stdev == 0:
            rep.add(IngestWarning(
                code=WarningCode.SUSPICIOUS_SCORE_DISTRIBUTION,
                severity=WarningSeverity.WARNING,
                message="All students scored identically — wrong answer key "
                        "or corrupted file?", context={"mean_frac": mean_frac}))
        elif mean_frac <= chance + 0.03:
            rep.add(IngestWarning(
                code=WarningCode.SUSPICIOUS_SCORE_DISTRIBUTION,
                severity=WarningSeverity.WARNING,
                message=f"Class mean ({mean_frac:.0%}) is at chance level — "
                        f"the answer key may belong to a different exam or booklet",
                context={"mean_frac": round(mean_frac, 3)}))
        elif mean_frac >= 0.97:
            rep.add(IngestWarning(
                code=WarningCode.SUSPICIOUS_SCORE_DISTRIBUTION,
                severity=WarningSeverity.WARNING,
                message=f"Class mean ({mean_frac:.0%}) is implausibly high — "
                        f"verify the upload contains responses, not the key",
                context={"mean_frac": round(mean_frac, 3)}))
    return rep
