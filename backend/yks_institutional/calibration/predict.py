"""Prediction hook + residual logging.

The institutional pipeline ends at (projected TYT/AYT nets, OBP). Score->rank
belongs to the EXISTING YKS Radar engine (integrated API / placement engine).
This module defines the seam:

  ScoreRankEngine protocol  <- implement with the real engine (thin adapter
                               around the integrated API; see wire_real_engine
                               docstring below)
  PlaceholderEngine         <- dev/test stand-in, clearly labeled, monotone and
                               convention-correct (lower rank = better) but NOT
                               calibrated. Never ship predictions from it.

Every prediction is logged to `residuals` with a null outcome at creation time.
When official YKS results arrive, db.record_outcome() closes them at
source="user_official_result" — the 4x-weight source class from the core
calibration module. This table is the moat's training data.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Protocol

from ..db import Database
from ..schemas import (AbilityEstimate, RankPrediction, ResidualRecord,
                       WarningCode, normalize_obp)
from ..stats.ability import project_nets


class ScoreRankEngine(Protocol):
    def score(self, tyt_net: float, ayt_net: float, obp: Optional[float],
              score_type: str) -> float: ...
    def rank_for_score(self, score: float, score_type: str) -> int: ...


class PlaceholderEngine:
    """DEV ONLY. Monotone score->rank curve with plausible shape; replace with
    the real integrated API before any user-facing output.

    Score: raw-net weighting consistent with the ÖSYM two-stage structure
    (TYT x 0.40 + AYT x 0.60 on scaled points, + OBP x 0.12). Net->point scaling
    here is linear per section, which the real engine does properly per-subject.
    """
    engine_name = "PLACEHOLDER_DO_NOT_SHIP"

    # crude anchor points (score -> rank), SAY-flavored, log-linear between
    _ANCHORS = [(560.0, 1_000), (520.0, 10_000), (480.0, 40_000),
                (440.0, 100_000), (400.0, 220_000), (360.0, 450_000),
                (320.0, 800_000), (280.0, 1_400_000), (200.0, 2_400_000),
                (90.0, 3_500_000)]

    def score(self, tyt_net, ayt_net, obp, score_type):
        tyt_pts = 100.0 + tyt_net * (400.0 / 120.0)   # 120 TYT questions
        ayt_pts = 100.0 + ayt_net * (400.0 / 80.0)    # 80 AYT questions
        base = tyt_pts * 0.40 + ayt_pts * 0.60
        return base + (obp * 0.12 if obp is not None else 0.0)

    def rank_for_score(self, score, score_type):
        import math
        a = self._ANCHORS
        if score >= a[0][0]:
            return a[0][1]
        if score <= a[-1][0]:
            return a[-1][1]
        for (s1, r1), (s2, r2) in zip(a, a[1:]):
            if s2 <= score <= s1:
                t = (s1 - score) / (s1 - s2)
                return int(round(math.exp(
                    math.log(r1) + t * (math.log(r2) - math.log(r1)))))
        return a[-1][1]


def predict_and_log(db: Database, *, student_id: str,
                    estimates: list[AbilityEstimate],
                    engine: ScoreRankEngine,
                    score_type: str = "SAY",
                    obp_raw: Optional[float] = None,
                    as_of: Optional[date] = None) -> RankPrediction:
    """Ability -> projected nets -> score -> rank interval; persist prediction
    AND open residual atomically. Convention: rank_low is the BETTER (smaller)
    boundary."""
    as_of = as_of or date.today()
    obp, obp_flags = normalize_obp(obp_raw)

    proj = project_nets(estimates)
    flags = list(obp_flags)
    # AYT-missing is visible as projected_ayt_net == 0 and surfaced by reports

    score_mid = engine.score(proj["tyt_net"], proj["ayt_net"], obp, score_type)
    score_hi = engine.score(proj["tyt_net_high"], proj["ayt_net_high"], obp, score_type)
    score_lo = engine.score(proj["tyt_net_low"], proj["ayt_net_low"], obp, score_type)

    rank_mid = engine.rank_for_score(score_mid, score_type)
    rank_low = engine.rank_for_score(score_hi, score_type)    # better score -> smaller rank
    rank_high = engine.rank_for_score(score_lo, score_type)
    # enforce ordering defensively
    rank_low, rank_high = min(rank_low, rank_high), max(rank_low, rank_high)

    pred = RankPrediction(
        student_id=student_id, as_of=as_of, score_type=score_type,
        projected_tyt_net=round(proj["tyt_net"], 2),
        projected_ayt_net=round(proj["ayt_net"], 2),
        obp_used=obp, score_estimate=round(score_mid, 2),
        rank_mid=rank_mid, rank_low=rank_low, rank_high=rank_high,
        flags=flags,
        engine=getattr(engine, "engine_name", engine.__class__.__name__))
    db.add_prediction(pred)
    db.add_residual(ResidualRecord(
        student_id=student_id, prediction_id=pred.prediction_id,
        predicted_rank_mid=rank_mid, predicted_rank_low=rank_low,
        predicted_rank_high=rank_high, predicted_at=as_of,
        score_type=score_type))
    return pred


def residual_summary(db: Database) -> dict:
    """MAE + interval coverage over closed residuals; the institutional
    counterpart of backtest.py's metrics."""
    closed = db.closed_residuals()
    if not closed:
        return {"n_closed": 0, "n_open": len(db.open_residuals()),
                "mae": None, "coverage": None}
    abs_err = [abs(r.residual) for r in closed]
    w = [r.sample_weight for r in closed]
    return {
        "n_closed": len(closed),
        "n_open": len(db.open_residuals()),
        "mae": sum(abs_err) / len(abs_err),
        "weighted_mae": sum(e * wi for e, wi in zip(abs_err, w)) / sum(w),
        "coverage": sum(1 for r in closed if r.covered) / len(closed),
    }


def wire_real_engine():
    """HOW TO REPLACE PlaceholderEngine (do this before demo day):

    from yks_radar.integrated_api import IntegratedAPI   # existing project code

    class RealEngine:
        engine_name = "yks_radar_integrated_v1"
        def __init__(self):
            self.api = IntegratedAPI()
        def score(self, tyt_net, ayt_net, obp, score_type):
            return self.api.compute_score(tyt_net=tyt_net, ayt_net=ayt_net,
                                          obp=obp, score_type=score_type)
        def rank_for_score(self, score, score_type):
            return self.api.rank_from_score(score, score_type)

    Then pass RealEngine() to predict_and_log. The placement engine and the
    114 department forecasts consume rank_mid/low/high unchanged
    (rank_margin = student_rank - threshold; negative = competitive).
    """
    raise NotImplementedError
