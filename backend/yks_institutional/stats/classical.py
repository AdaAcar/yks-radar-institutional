"""Classical test theory item statistics (knowledge layer v0).

Per question, on every ingest:
  * p_value: fraction of respondents answering correctly (blank counts as wrong
    for difficulty purposes — matches how students experience the item).
  * point_biserial: corrected item-total correlation (item score vs. total
    score EXCLUDING the item, so the item doesn't correlate with itself).

Degenerate cases return None rather than fake numbers, with warnings emitted
by the caller. These columns are the v1 stand-ins for irt_difficulty /
irt_discrimination; the schema keeps both so IRT can land without migration.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class ItemStats:
    position: int
    p_value: float
    point_biserial: Optional[float]
    n: int


def compute_item_stats(score_matrix: list[list[int]]) -> list[ItemStats]:
    """score_matrix: rows = students, cols = questions, values in {0,1}.

    Rows must be complete (callers filter out length-mismatched rows upstream).
    """
    if not score_matrix:
        return []
    n_students = len(score_matrix)
    n_items = len(score_matrix[0])
    totals = [sum(row) for row in score_matrix]
    out: list[ItemStats] = []

    for j in range(n_items):
        col = [row[j] for row in score_matrix]
        p = sum(col) / n_students
        rest = [totals[i] - col[i] for i in range(n_students)]
        rpb = _point_biserial(col, rest)
        out.append(ItemStats(position=j + 1, p_value=p,
                             point_biserial=rpb, n=n_students))
    return out


def _point_biserial(item: list[int], rest: list[float]) -> Optional[float]:
    n = len(item)
    if n < 3:
        return None
    p = sum(item) / n
    if p == 0.0 or p == 1.0:
        return None                          # zero-variance item
    mean_rest = sum(rest) / n
    var_rest = sum((x - mean_rest) ** 2 for x in rest) / n
    if var_rest == 0:
        return None
    sd_rest = math.sqrt(var_rest)
    mean_1 = sum(r for it, r in zip(item, rest) if it == 1) / sum(item)
    mean_0 = sum(r for it, r in zip(item, rest) if it == 0) / (n - sum(item))
    return (mean_1 - mean_0) / sd_rest * math.sqrt(p * (1 - p))
