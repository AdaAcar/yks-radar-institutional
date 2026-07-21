"""Report data layer: plain JSON dicts consumed by the React/PDF frontend.

Contract rule: the frontend reads these shapes; if a report "needs" a field
that isn't here, that's a contract change, not a frontend hack.

Plain-language rule: user-facing strings avoid statistical jargon. Numbers are
rounded; uncertainty is phrased as ranges, not standard errors.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date

from ..db import Database
from ..schemas import Subject

SUBJECT_LABELS_TR = {
    Subject.TYT_TURKCE: "TYT Türkçe", Subject.TYT_MATEMATIK: "TYT Matematik",
    Subject.TYT_SOSYAL: "TYT Sosyal", Subject.TYT_FEN: "TYT Fen",
    Subject.AYT_MATEMATIK: "AYT Matematik", Subject.AYT_FIZIK: "AYT Fizik",
    Subject.AYT_KIMYA: "AYT Kimya", Subject.AYT_BIYOLOJI: "AYT Biyoloji",
    Subject.AYT_EDEBIYAT: "AYT Edebiyat", Subject.AYT_TARIH1: "AYT Tarih-1",
    Subject.AYT_COGRAFYA1: "AYT Coğrafya-1",
}


def student_report(db: Database, student_id: str) -> dict:
    results = db.results_for_student(student_id)
    abilities = db.latest_abilities(student_id)

    exams = []
    for res in sorted(results, key=lambda r: r.exam_id):
        exams.append({
            "exam_id": res.exam_id,
            "tyt_net": round(res.total_net_tyt, 2),
            "ayt_net": round(res.total_net_ayt, 2),
            "subjects": [{
                "subject": SUBJECT_LABELS_TR.get(n.subject, n.subject.value),
                "net": round(n.net, 2), "correct": n.correct,
                "wrong": n.wrong, "blank": n.blank,
            } for n in res.nets],
        })

    strengths, weaknesses = [], []
    for a in sorted(abilities, key=lambda x: x.theta - x.cohort_mean, reverse=True):
        entry = {
            "subject": SUBJECT_LABELS_TR.get(a.subject, a.subject.value),
            "level": round(a.theta * 100),                 # "out of 100" plain scale
            "class_average": round(a.cohort_mean * 100),
            "based_on_exams": a.n_exams,
        }
        (strengths if a.theta >= a.cohort_mean else weaknesses).append(entry)

    return {
        "student_id": student_id,
        "exams": exams,
        "strengths": strengths[:4],
        "focus_areas": list(reversed(weaknesses))[:4],
        "n_exams": len(results),
    }


def teacher_report(db: Database, exam_ids: list[str]) -> dict:
    """Topic/subject trends across exams: 'geometry deteriorating' is a
    p-value delta over time — no model needed, just the knowledge layer."""
    timeline = []
    for exam_id in exam_ids:
        qs = db.questions_for_exam(exam_id)
        by_topic: dict[str, list[float]] = defaultdict(list)
        for q in qs:
            if q.p_value is None:
                continue
            key = q.topic or SUBJECT_LABELS_TR.get(q.subject, q.subject.value)
            by_topic[key].append(q.p_value)
        timeline.append({
            "exam_id": exam_id,
            "topics": {t: round(statistics.mean(v) * 100)
                       for t, v in by_topic.items()},
        })

    trends = []
    if len(timeline) >= 2:
        first, last = timeline[0]["topics"], timeline[-1]["topics"]
        for topic in sorted(set(first) & set(last)):
            delta = last[topic] - first[topic]
            if abs(delta) >= 5:
                trends.append({
                    "topic": topic,
                    "change": delta,
                    "direction": "improving" if delta > 0 else "declining",
                    "from": first[topic], "to": last[topic],
                })
    trends.sort(key=lambda t: t["change"])
    return {"timeline": timeline, "trends": trends}


def principal_dashboard(db: Database, school_id: str,
                        exam_ids: list[str]) -> dict:
    """School-level distribution and trajectory."""
    per_exam = []
    for exam_id in exam_ids:
        results = db.results_for_exam(exam_id)
        if not results:
            continue
        tyt = sorted(r.total_net_tyt for r in results)
        per_exam.append({
            "exam_id": exam_id,
            "n_students": len(results),
            "tyt_net_mean": round(statistics.mean(tyt), 1),
            "tyt_net_median": round(tyt[len(tyt) // 2], 1),
            "tyt_net_p25": round(tyt[len(tyt) // 4], 1),
            "tyt_net_p75": round(tyt[(3 * len(tyt)) // 4], 1),
        })
    trajectory = None
    if len(per_exam) >= 2:
        delta = per_exam[-1]["tyt_net_mean"] - per_exam[0]["tyt_net_mean"]
        trajectory = {"tyt_net_change": round(delta, 1),
                      "direction": "up" if delta > 0 else
                                   ("down" if delta < 0 else "flat")}
    return {"school_id": school_id, "exams": per_exam, "trajectory": trajectory,
            "as_of": date.today().isoformat()}
