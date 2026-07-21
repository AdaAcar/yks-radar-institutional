"""Upload adapters: turn heterogeneous school files into one canonical shape.

Canonical output: UploadBatch
  * answer_key: list of canonical tokens ("A".."E") or None if key comes separately
  * rows: [{student_no, name?, answers: [token|None, ...]}]

Supported input formats (v1):
  * CSV (utf-8 / utf-8-sig / latin-5 fallback)
  * XLSX (first sheet)

Answer notations auto-detected and normalized:
  * Letters  A B C D E   (case-insensitive)
  * Digits   1 2 3 4 5   -> A B C D E
  * TRUE/FALSE (T/F, D/Y Turkish dogru/yanlis) -> "T"/"F", option_count=2
  * Blank / "-" / "*" / "BOS" -> None
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Optional

from ..schemas import IngestWarning, WarningCode, WarningSeverity

LETTER_SET = set("ABCDE")
DIGIT_MAP = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E"}
TF_MAP = {"T": "T", "TRUE": "T", "D": "T", "DOGRU": "T", "DOĞRU": "T",
          "F": "F", "FALSE": "F", "Y": "F", "YANLIS": "F", "YANLIŞ": "F"}
BLANK_TOKENS = {"", "-", "*", ".", "BOS", "BOŞ", "NA", "N/A", "X"}

STUDENT_NO_HEADERS = {"student no", "student_no", "studentno", "ogrenci no",
                      "öğrenci no", "ogrenci_no", "no", "numara", "okul no",
                      "okul numarasi", "okul numarası", "id"}
NAME_HEADERS = {"name", "ad", "adi", "adı", "ad soyad", "isim", "student name",
                "adi soyadi", "adı soyadı"}
KEY_ROW_TOKENS = {"answer key", "cevap anahtari", "cevap anahtarı", "key", "anahtar"}


@dataclass
class StudentRow:
    student_no: str
    answers: list[Optional[str]]
    name: Optional[str] = None
    source_row: int = 0


@dataclass
class UploadBatch:
    rows: list[StudentRow] = field(default_factory=list)
    answer_key: Optional[list[str]] = None
    n_questions: int = 0
    detected_format: str = "unknown"        # letters | digits | truefalse
    option_count: int = 5
    warnings: list[IngestWarning] = field(default_factory=list)


def _normalize_token(raw, fmt: str) -> tuple[Optional[str], bool]:
    """Return (canonical_token_or_None, ok). ok=False means unparseable."""
    if raw is None:
        return None, True
    s = str(raw).strip().upper()
    if s in BLANK_TOKENS:
        return None, True
    if fmt == "letters":
        return (s, True) if s in LETTER_SET else (None, False)
    if fmt == "digits":
        return (DIGIT_MAP[s], True) if s in DIGIT_MAP else (None, False)
    if fmt == "truefalse":
        return (TF_MAP[s], True) if s in TF_MAP else (None, False)
    return None, False


def detect_format(tokens: list[str]) -> str:
    """Vote over non-blank tokens. Ambiguity resolved by majority; ties -> unknown."""
    votes = {"letters": 0, "digits": 0, "truefalse": 0}
    for raw in tokens:
        s = str(raw).strip().upper()
        if s in BLANK_TOKENS:
            continue
        # T/F first: "D" is both a letter and Turkish dogru — disambiguate by
        # checking the overall alphabet below, not per-token.
        if s in LETTER_SET:
            votes["letters"] += 1
        if s in DIGIT_MAP:
            votes["digits"] += 1
        if s in TF_MAP:
            votes["truefalse"] += 1
    # If tokens include letters outside {D,F(also letter)} beyond TF alphabet,
    # letters wins; if all tokens are within TF alphabet only, prefer truefalse
    # only when letters like A/B/C/E never appear.
    non_blank = [str(t).strip().upper() for t in tokens
                 if str(t).strip().upper() not in BLANK_TOKENS]
    if non_blank and all(t in TF_MAP for t in non_blank):
        return "truefalse"
    best = max(votes, key=votes.get)
    if votes[best] == 0:
        return "unknown"
    # digits vs letters can't genuinely collide (disjoint alphabets)
    return best


def _find_columns(header: list[str]) -> tuple[Optional[int], Optional[int], list[int]]:
    """Return (student_no_idx, name_idx, answer_col_idxs)."""
    norm = [str(h).strip().lower() for h in header]
    no_idx = next((i for i, h in enumerate(norm) if h in STUDENT_NO_HEADERS), None)
    name_idx = next((i for i, h in enumerate(norm) if h in NAME_HEADERS), None)
    answer_idxs = [i for i in range(len(header))
                   if i not in {no_idx, name_idx} and str(header[i]).strip() != ""]
    return no_idx, name_idx, answer_idxs


def parse_table(rows: list[list], filename: str = "") -> UploadBatch:
    """Core parser over a raw table (list of rows). Shared by CSV and XLSX paths."""
    batch = UploadBatch()
    if not rows:
        batch.warnings.append(IngestWarning(
            code=WarningCode.EMPTY_RESPONSE_ROW, severity=WarningSeverity.FATAL,
            message="File contains no rows", context={"filename": filename}))
        return batch

    header = [("" if c is None else str(c)) for c in rows[0]]
    no_idx, name_idx, answer_idxs = _find_columns(header)
    if no_idx is None:
        # No recognizable header: assume col0 = student no, rest = answers
        no_idx, name_idx = 0, None
        answer_idxs = list(range(1, len(header)))
        data_rows = rows
        batch.warnings.append(IngestWarning(
            code=WarningCode.UNKNOWN_FORMAT, severity=WarningSeverity.INFO,
            message="No header row detected; assuming first column is student number",
            context={"filename": filename}))
    else:
        data_rows = rows[1:]

    batch.n_questions = len(answer_idxs)

    # Pull answer-key row if embedded (student_no cell says 'answer key' etc.)
    key_row = None
    body: list[tuple[int, list]] = []
    for i, r in enumerate(data_rows):
        cell = str(r[no_idx]).strip().lower() if no_idx < len(r) and r[no_idx] is not None else ""
        if cell in KEY_ROW_TOKENS:
            key_row = r
        else:
            body.append((i + (1 if data_rows is not rows else 0) + 1, r))

    # Detect notation over all answer cells
    all_tokens = []
    sample_rows = ([key_row] if key_row else []) + [r for _, r in body]
    for r in sample_rows:
        for idx in answer_idxs:
            if idx < len(r):
                all_tokens.append(r[idx])
    fmt = detect_format(all_tokens)
    if fmt == "unknown":
        batch.warnings.append(IngestWarning(
            code=WarningCode.UNKNOWN_FORMAT, severity=WarningSeverity.FATAL,
            message="Could not detect answer notation (letters/digits/true-false)",
            context={"filename": filename}))
        return batch
    batch.detected_format = fmt
    batch.option_count = 2 if fmt == "truefalse" else 5

    bad_cells = 0
    if key_row is not None:
        key: list[Optional[str]] = []
        for idx in answer_idxs:
            raw = key_row[idx] if idx < len(key_row) else None
            tok, ok = _normalize_token(raw, fmt)
            if not ok:
                bad_cells += 1
                tok = None
            key.append(tok)
        if any(t is None for t in key):
            batch.warnings.append(IngestWarning(
                code=WarningCode.ANSWER_KEY_LENGTH_MISMATCH,
                severity=WarningSeverity.FATAL,
                message="Answer key row has blank or unreadable entries",
                context={"filename": filename,
                         "blank_positions": [i + 1 for i, t in enumerate(key) if t is None]}))
            return batch
        batch.answer_key = [t for t in key if t is not None]

    for rowno, r in body:
        raw_no = r[no_idx] if no_idx < len(r) else None
        student_no = "" if raw_no is None else str(raw_no).strip()
        # xlsx often gives numbers as floats: 1278.0 -> "1278"
        if student_no.endswith(".0"):
            student_no = student_no[:-2]
        name = None
        if name_idx is not None and name_idx < len(r) and r[name_idx] is not None:
            name = str(r[name_idx]).strip() or None
        answers: list[Optional[str]] = []
        for idx in answer_idxs:
            raw = r[idx] if idx < len(r) else None
            tok, ok = _normalize_token(raw, fmt)
            if not ok:
                bad_cells += 1
                tok = None
            answers.append(tok)
        if not student_no:
            batch.warnings.append(IngestWarning(
                code=WarningCode.EMPTY_RESPONSE_ROW, severity=WarningSeverity.ERROR,
                message=f"Row {rowno}: missing student number, row skipped",
                context={"row": rowno}))
            continue
        batch.rows.append(StudentRow(student_no=student_no, answers=answers,
                                     name=name, source_row=rowno))

    if bad_cells:
        batch.warnings.append(IngestWarning(
            code=WarningCode.MIXED_FORMAT, severity=WarningSeverity.WARNING,
            message=f"{bad_cells} answer cell(s) did not match detected notation "
                    f"'{fmt}' and were treated as blank",
            context={"bad_cells": bad_cells, "format": fmt}))
    return batch


# ---------------------------------------------------------------------------
# File-level entry points
# ---------------------------------------------------------------------------

def parse_csv_bytes(data: bytes, filename: str = "") -> UploadBatch:
    text = None
    for enc in ("utf-8-sig", "utf-8", "iso-8859-9"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        b = UploadBatch()
        b.warnings.append(IngestWarning(
            code=WarningCode.UNKNOWN_FORMAT, severity=WarningSeverity.FATAL,
            message="Could not decode CSV (tried utf-8, utf-8-sig, iso-8859-9)",
            context={"filename": filename}))
        return b
    # deterministic delimiter detection: max count in first non-empty line
    # (csv.Sniffer is unreliable on wide files where its sample cuts mid-row)
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    delim = max(",;\t", key=first_line.count)
    if first_line.count(delim) == 0:
        delim = ","
    rows = [row for row in csv.reader(io.StringIO(text), delimiter=delim)]
    return parse_table(rows, filename)


def parse_xlsx_bytes(data: bytes, filename: str = "") -> UploadBatch:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return parse_table(rows, filename)


def parse_upload(data: bytes, filename: str) -> UploadBatch:
    fn = filename.lower()
    if fn.endswith(".csv") or fn.endswith(".txt"):
        return parse_csv_bytes(data, filename)
    if fn.endswith(".xlsx") or fn.endswith(".xlsm"):
        return parse_xlsx_bytes(data, filename)
    # last resort: try CSV then XLSX
    batch = parse_csv_bytes(data, filename)
    if any(w.severity == WarningSeverity.FATAL for w in batch.warnings):
        try:
            return parse_xlsx_bytes(data, filename)
        except Exception:
            return batch
    return batch
