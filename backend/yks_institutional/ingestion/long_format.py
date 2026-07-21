"""Long-format adapter (ported from the ChatGPT deliverable, adapted).

Some optic-reader and publisher exports emit one row per (student, question)
rather than a wide grid:

    student_no,question_no,answer
    1001,1,A
    1001,2,C

This module pivots that shape into the canonical UploadBatch so the ENTIRE
existing pipeline (matching, validation, persistence, item stats) applies
unchanged. One ingestion path, two входные formats.

Kept from the original: header-alias resolution (Turkish + English),
duplicate (student,question) detection with later-row-ignored semantics.
Changed: column-resolution failures become FATAL warnings instead of raised
exceptions (never fail silently — but also never crash the upload route), and
unparseable answers become warned blanks instead of skipped rows, matching the
wide-path convention.
"""
from __future__ import annotations

from collections import defaultdict

from ..schemas import IngestWarning, WarningCode, WarningSeverity
from .adapters import (StudentRow, UploadBatch, detect_format,
                       parse_csv_bytes, parse_xlsx_bytes, _normalize_token)

ALIASES = {
    "student_no": {"student_number", "student_no", "studentno", "ogrenci_no",
                   "ogrenci no", "öğrenci no", "okul no", "no", "numara", "id"},
    "question_no": {"question_number", "question_no", "questionno", "soru_no",
                    "soru no", "soru", "item", "q"},
    "answer": {"answer", "cevap", "response", "yanit", "yanıt"},
}


def _norm_header(h: object) -> str:
    s = str(h).strip().lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"),
                 ("ö", "o"), ("ç", "c")):
        s = s.replace(a, b)
    return s


def _resolve(header: list) -> tuple[dict[str, int] | None, IngestWarning | None]:
    norm = [_norm_header(h) for h in header]
    out: dict[str, int] = {}
    for canonical, aliases in ALIASES.items():
        # normalize aliases through the same folding
        folded = {_norm_header(a) for a in aliases}
        hits = [i for i, h in enumerate(norm) if h in folded]
        if len(hits) != 1:
            return None, IngestWarning(
                code=WarningCode.UNKNOWN_FORMAT, severity=WarningSeverity.FATAL,
                message=f"Long format needs exactly one '{canonical}' column; "
                        f"found {len(hits)} among headers {header[:6]}",
                context={"canonical": canonical, "n_hits": len(hits)})
        out[canonical] = hits[0]
    return out, None


def is_long_format(raw_rows: list[list]) -> bool:
    """A file is long-format if its header resolves to the three canonical
    columns AND has few total columns (wide grids have dozens)."""
    if not raw_rows or len(raw_rows[0]) > 6:
        return False
    cols, err = _resolve([("" if c is None else c) for c in raw_rows[0]])
    return cols is not None


def pivot_long_to_batch(raw_rows: list[list]) -> UploadBatch:
    """Pivot long rows into the canonical wide UploadBatch."""
    batch = UploadBatch()
    header = [("" if c is None else c) for c in raw_rows[0]]
    cols, err = _resolve(header)
    if cols is None:
        batch.warnings.append(err)
        return batch

    triples: list[tuple[str, int, object, int]] = []   # (no, q, raw, source_row)
    max_q = 0
    for i, r in enumerate(raw_rows[1:], start=2):
        def cell(k):
            idx = cols[k]
            return r[idx] if idx < len(r) else None
        no = str(cell("student_no") or "").strip()
        if no.endswith(".0"):
            no = no[:-2]
        try:
            q = int(float(str(cell("question_no")).strip()))
        except (TypeError, ValueError):
            batch.warnings.append(IngestWarning(
                code=WarningCode.RESPONSE_LENGTH_MISMATCH,
                severity=WarningSeverity.ERROR,
                message=f"Row {i}: question number is not an integer; row skipped",
                context={"row": i}))
            continue
        if not no or q < 1:
            batch.warnings.append(IngestWarning(
                code=WarningCode.EMPTY_RESPONSE_ROW,
                severity=WarningSeverity.ERROR,
                message=f"Row {i}: missing student number or bad question "
                        f"number; row skipped", context={"row": i}))
            continue
        triples.append((no, q, cell("answer"), i))
        max_q = max(max_q, q)

    if not triples:
        batch.warnings.append(IngestWarning(
            code=WarningCode.EMPTY_RESPONSE_ROW, severity=WarningSeverity.FATAL,
            message="Long-format file contains no usable response rows",
            context={}))
        return batch

    fmt = detect_format([t[2] for t in triples])
    if fmt == "unknown":
        batch.warnings.append(IngestWarning(
            code=WarningCode.UNKNOWN_FORMAT, severity=WarningSeverity.FATAL,
            message="Could not detect answer notation in long-format file",
            context={}))
        return batch
    batch.detected_format = fmt
    batch.option_count = 2 if fmt == "truefalse" else 5
    batch.n_questions = max_q

    grids: dict[str, list] = defaultdict(lambda: [None] * max_q)
    first_rows: dict[str, int] = {}
    dup_cells = 0
    bad_cells = 0
    for no, q, raw, srow in triples:
        first_rows.setdefault(no, srow)
        if grids[no][q - 1] is not None:
            dup_cells += 1
            continue                       # later row ignored (GPT semantics)
        tok, ok = _normalize_token(raw, fmt)
        if not ok:
            bad_cells += 1
            tok = None
        grids[no][q - 1] = tok

    if dup_cells:
        batch.warnings.append(IngestWarning(
            code=WarningCode.DUPLICATE_STUDENT_ROW,
            severity=WarningSeverity.WARNING,
            message=f"{dup_cells} duplicate (student, question) cell(s); "
                    f"first occurrence kept",
            context={"dup_cells": dup_cells}))
    if bad_cells:
        batch.warnings.append(IngestWarning(
            code=WarningCode.MIXED_FORMAT, severity=WarningSeverity.WARNING,
            message=f"{bad_cells} answer cell(s) did not match detected "
                    f"notation '{fmt}' and were treated as blank",
            context={"bad_cells": bad_cells, "format": fmt}))

    for no, answers in grids.items():
        batch.rows.append(StudentRow(student_no=no, answers=answers,
                                     source_row=first_rows[no]))
    batch.rows.sort(key=lambda r: r.source_row)
    return batch


def parse_upload_any(data: bytes, filename: str) -> UploadBatch:
    """Entry point that handles BOTH wide grids and long-format files.
    Detection is structural (header shape), never guessed from content."""
    from .adapters import parse_table
    import csv as _csv, io as _io

    fn = filename.lower()
    raw_rows: list[list] | None = None
    if fn.endswith((".csv", ".txt")):
        for enc in ("utf-8-sig", "utf-8", "iso-8859-9"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                text = None
        if text is not None:
            first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
            delim = max(",;\t", key=first_line.count)
            raw_rows = [r for r in _csv.reader(_io.StringIO(text),
                                               delimiter=delim if first_line.count(delim) else ",")]
    elif fn.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(_io.BytesIO(data), read_only=True, data_only=True)
        raw_rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
        wb.close()

    if raw_rows is not None and is_long_format(raw_rows):
        return pivot_long_to_batch(raw_rows)
    from .adapters import parse_upload
    return parse_upload(data, filename)
