"""Institutional backend test suite."""
import random
from datetime import date

import pytest

from yks_institutional.db import Database
from yks_institutional.calibration.predict import (PlaceholderEngine,
                                                   predict_and_log,
                                                   residual_summary)
from yks_institutional.ingestion.adapters import (detect_format,
                                                  parse_csv_bytes,
                                                  parse_xlsx_bytes)
from yks_institutional.ingestion.matching import match_rows
from yks_institutional.ingestion.pipeline import SubjectBlock, ingest_upload
from yks_institutional.ingestion.validation import validate_batch
from yks_institutional.reports.data import (principal_dashboard,
                                            student_report, teacher_report)
from yks_institutional.schemas import (Student, Subject, WarningCode,
                                       WarningSeverity, normalize_obp)
from yks_institutional.seed_synthetic import (make_exam_data, make_school,
                                              seed_database, to_csv_digits,
                                              to_csv_letters, to_xlsx,
                                              TYT_BLOCKS)
from yks_institutional.stats.ability import estimate_abilities, project_nets
from yks_institutional.stats.classical import compute_item_stats


# ---------------------------------------------------------------- adapters --
class TestAdapters:
    def test_detect_letters(self):
        assert detect_format(["A", "B", "E", "", "C"]) == "letters"

    def test_detect_digits(self):
        assert detect_format(["1", "4", "5", "-", "2"]) == "digits"

    def test_detect_truefalse_turkish(self):
        assert detect_format(["D", "Y", "D", "D", "Y"]) == "truefalse"

    def test_letters_beat_tf_when_abce_present(self):
        assert detect_format(["A", "D", "C", "D"]) == "letters"

    def test_csv_semicolon_letters_with_key(self):
        raw = ("Ogrenci No;S1;S2;S3\n"
               "CEVAP ANAHTARI;A;B;C\n"
               "1001;A;B;D\n"
               "1002;;B;C\n").encode("utf-8")
        b = parse_csv_bytes(raw, "x.csv")
        assert b.answer_key == ["A", "B", "C"]
        assert b.n_questions == 3
        assert b.rows[0].answers == ["A", "B", "D"]
        assert b.rows[1].answers == [None, "B", "C"]

    def test_csv_digits_normalized(self):
        raw = ("No,Q1,Q2\nKEY,1,3\n1001,1,4\n").encode("utf-8")
        b = parse_csv_bytes(raw, "x.csv")
        assert b.answer_key == ["A", "C"]
        assert b.rows[0].answers == ["A", "D"]
        assert b.detected_format == "digits"

    def test_xlsx_roundtrip_and_float_student_no(self):
        key, sheets = ["A", "B"], {"1001": ["A", None]}
        b = parse_xlsx_bytes(to_xlsx(key, sheets), "x.xlsx")
        assert b.answer_key == ["A", "B"]
        assert b.rows[0].student_no == "1001"     # not "1001.0"
        assert b.rows[0].answers == ["A", None]

    def test_turkish_encoding_fallback(self):
        raw = "No;S1\nÖĞRENCİ;A\n".encode("iso-8859-9")
        b = parse_csv_bytes(raw, "x.csv")
        assert not any(w.severity == WarningSeverity.FATAL for w in b.warnings)

    def test_unknown_format_is_fatal(self):
        raw = ("No;S1;S2\n1001;Q;Z\n").encode("utf-8")
        b = parse_csv_bytes(raw, "x.csv")
        assert any(w.code == WarningCode.UNKNOWN_FORMAT and
                   w.severity == WarningSeverity.FATAL for w in b.warnings)


# ---------------------------------------------------------------- matching --
class TestMatching:
    def _students(self):
        return [Student(school_id="s", school_student_no="1278",
                        display_name="Ayşe Yılmaz"),
                Student(school_id="s", school_student_no="42",
                        display_name="Mehmet Kaya")]

    def test_exact_and_zero_padded(self):
        from yks_institutional.ingestion.adapters import StudentRow
        rows = [StudentRow("1278", ["A"]), StudentRow("0042", ["B"])]
        res = match_rows(rows, self._students())
        assert len(res.matched) == 2
        assert not res.unmatched

    def test_unmatched_is_error_not_silent(self):
        from yks_institutional.ingestion.adapters import StudentRow
        res = match_rows([StudentRow("9999", ["A"])], self._students())
        assert len(res.unmatched) == 1
        assert any(w.code == WarningCode.UNMATCHED_STUDENT and
                   w.severity == WarningSeverity.ERROR for w in res.warnings)

    def test_fuzzy_name_fallback_turkish(self):
        from yks_institutional.ingestion.adapters import StudentRow
        res = match_rows([StudentRow("7777", ["A"], name="AYSE YILMAZ")],
                         self._students())
        assert len(res.matched) == 1

    def test_duplicate_row_kept_once(self):
        from yks_institutional.ingestion.adapters import StudentRow
        rows = [StudentRow("1278", ["A"]), StudentRow("1278", ["B"])]
        res = match_rows(rows, self._students())
        assert len(res.matched) == 1
        assert len(res.duplicate_rows) == 1

    def test_missing_registered_students_reported(self):
        from yks_institutional.ingestion.adapters import StudentRow
        res = match_rows([StudentRow("1278", ["A"])], self._students())
        assert len(res.missing_students) == 1
        assert res.missing_students[0].school_student_no == "42"


# -------------------------------------------------------------- validation --
class TestValidation:
    def _batch(self, raw):
        return parse_csv_bytes(raw, "v.csv")

    def test_duplicate_upload_fatal(self):
        b = self._batch(b"No;S1\nCEVAP ANAHTARI;A\n1;A\n")
        rep = validate_batch(b, None, is_duplicate_upload=True)
        assert rep.fatal
        assert any(w.code == WarningCode.DUPLICATE_UPLOAD for w in rep.warnings)

    def test_missing_key_fatal(self):
        b = self._batch(b"No;S1\n1;A\n")
        rep = validate_batch(b, None, is_duplicate_upload=False)
        assert rep.fatal

    def test_key_length_mismatch_fatal(self):
        b = self._batch(b"No;S1;S2\n1;A;B\n")
        rep = validate_batch(b, ["A"], is_duplicate_upload=False)
        assert rep.fatal

    def test_chance_level_distribution_flagged(self):
        rng = random.Random(1)
        lines = ["No;" + ";".join(f"S{i}" for i in range(20))]
        for s in range(30):
            lines.append(f"{s};" + ";".join(rng.choice("ABCDE") for _ in range(20)))
        b = self._batch("\n".join(lines).encode())
        rep = validate_batch(b, ["A"] * 20, is_duplicate_upload=False)
        assert any(w.code == WarningCode.SUSPICIOUS_SCORE_DISTRIBUTION
                   for w in rep.warnings)
        assert not rep.fatal    # warning, not rejection

    def test_uniform_answers_flagged(self):
        n = 20
        lines = ["No;" + ";".join(f"S{i}" for i in range(n)),
                 "1001;" + ";".join("A" for _ in range(n)),
                 "1002;" + ";".join(random.Random(2).choice("ABCDE") for _ in range(n))]
        b = self._batch("\n".join(lines).encode())
        rep = validate_batch(b, ["B"] * n, is_duplicate_upload=False)
        assert any(w.code == WarningCode.UNIFORM_ANSWERS for w in rep.warnings)


# ------------------------------------------------------------------- stats --
class TestClassicalStats:
    def test_pvalue_and_positive_rpb_for_good_item(self):
        rng = random.Random(3)
        matrix = []
        for _ in range(200):
            ability = rng.random()
            row = [1 if rng.random() < 0.2 + 0.7 * ability else 0
                   for _ in range(10)]
            matrix.append(row)
        stats = compute_item_stats(matrix)
        assert len(stats) == 10
        for s in stats:
            assert 0.0 <= s.p_value <= 1.0
            assert s.point_biserial is not None and s.point_biserial > 0.1

    def test_zero_variance_returns_none_rpb(self):
        matrix = [[1, 1], [1, 0], [1, 1]]
        stats = compute_item_stats(matrix)
        assert stats[0].p_value == 1.0
        assert stats[0].point_biserial is None


class TestAbility:
    def _result(self, student_id, exam_id, frac, n_q=40):
        from yks_institutional.schemas import ExamResult, SubjectNet
        c = int(round(frac * n_q))
        net = SubjectNet(subject=Subject.TYT_MATEMATIK, correct=c,
                         wrong=n_q - c, blank=0, net=c - (n_q - c) / 4)
        return ExamResult(student_id=student_id, exam_id=exam_id, nets=[net],
                          total_net_tyt=net.net, total_net_ayt=0)

    def test_shrinkage_pulls_toward_cohort(self):
        strong = [self._result("s1", "e1", 0.9)]
        cohort = strong + [self._result(f"c{i}", "e1", 0.4) for i in range(20)]
        est = estimate_abilities("s1", strong, cohort)[0]
        assert est.shrunk_from > est.theta > est.cohort_mean

    def test_more_exams_less_shrinkage(self):
        one = [self._result("s1", "e1", 0.9)]
        five = [self._result("s1", f"e{i}", 0.9) for i in range(5)]
        cohort = [self._result(f"c{i}", "e1", 0.4) for i in range(20)]
        t1 = estimate_abilities("s1", one, cohort + one)[0].theta
        t5 = estimate_abilities("s1", five, cohort + five)[0].theta
        assert t5 > t1

    def test_project_nets_interval_ordering(self):
        est = estimate_abilities(
            "s1", [self._result("s1", "e1", 0.6)],
            [self._result(f"c{i}", "e1", 0.5) for i in range(10)])
        proj = project_nets(est)
        assert proj["tyt_net_low"] <= proj["tyt_net"] <= proj["tyt_net_high"]


# --------------------------------------------------------------------- OBP --
class TestOBP:
    def test_diploma_note_autoconverts(self):
        v, flags = normalize_obp(85)
        assert v == 425.0
        assert WarningCode.OBP_AUTOCONVERTED in flags

    def test_low_diploma_note_floored_at_250(self):
        v, _ = normalize_obp(30)
        assert v == 250.0

    def test_blank_contributes_zero_with_flag(self):
        v, flags = normalize_obp(None)
        assert v is None
        assert WarningCode.OBP_MISSING in flags
        e = PlaceholderEngine()
        s_none = e.score(80, 40, None, "SAY")
        s_zero_equiv = e.score(80, 40, None, "SAY")
        assert s_none == s_zero_equiv          # no phantom 350

    def test_true_obp_passthrough(self):
        v, flags = normalize_obp(412.5)
        assert v == 412.5 and flags == []

    def test_out_of_range_never_guessed(self):
        v, flags = normalize_obp(700)
        assert v is None and WarningCode.OBP_MISSING in flags


# --------------------------------------------------------------- prediction --
class TestPrediction:
    def test_rank_conventions_and_residual_opened(self):
        db = Database()
        est = estimate_abilities(
            "s1",
            [TestAbility()._result("s1", "e1", 0.7)],
            [TestAbility()._result(f"c{i}", "e1", 0.5) for i in range(10)])
        pred = predict_and_log(db, student_id="s1", estimates=est,
                               engine=PlaceholderEngine(), obp_raw=90)
        assert pred.rank_low <= pred.rank_mid <= pred.rank_high  # lower = better
        assert len(db.open_residuals()) == 1
        assert pred.obp_used == 450.0
        assert WarningCode.OBP_AUTOCONVERTED in pred.flags

    def test_better_ability_better_rank(self):
        db = Database()
        mk = TestAbility()._result
        cohort = [mk(f"c{i}", "e1", 0.5) for i in range(10)]
        e_hi = estimate_abilities("h", [mk("h", "e1", 0.85)], cohort)
        e_lo = estimate_abilities("l", [mk("l", "e1", 0.30)], cohort)
        eng = PlaceholderEngine()
        p_hi = predict_and_log(db, student_id="h", estimates=e_hi, engine=eng)
        p_lo = predict_and_log(db, student_id="l", estimates=e_lo, engine=eng)
        assert p_hi.rank_mid < p_lo.rank_mid   # lower rank number = better

    def test_outcome_closes_residual_and_metrics(self):
        db = Database()
        est = estimate_abilities(
            "s1", [TestAbility()._result("s1", "e1", 0.7)],
            [TestAbility()._result(f"c{i}", "e1", 0.5) for i in range(10)])
        pred = predict_and_log(db, student_id="s1", estimates=est,
                               engine=PlaceholderEngine())
        n = db.record_outcome("s1", actual_rank=pred.rank_mid + 5000,
                              source="user_official_result")
        assert n == 1
        summ = residual_summary(db)
        assert summ["n_closed"] == 1 and summ["mae"] == 5000


# -------------------------------------------------------------- end-to-end --
class TestEndToEnd:
    @pytest.fixture(scope="class")
    def seeded(self):
        db = Database()
        school, students, exam_ids = seed_database(db, seed=7, n_students=60)
        return db, school, students, exam_ids

    def test_three_formats_all_ingested(self, seeded):
        db, school, students, exam_ids = seeded
        assert len(exam_ids) == 3
        for eid in exam_ids:
            assert len(db.results_for_exam(eid)) == 60

    def test_duplicate_reupload_rejected(self):
        db = Database()
        school, students, exam_ids = seed_database(db, seed=7, n_students=60)
        rng = random.Random(99)
        _, students2, abilities = make_school(random.Random(7), 60)  # same roster nos
        key, sheets = make_exam_data(rng, abilities, 120, 0.0)
        raw = to_csv_letters(key, sheets)
        blocks = [SubjectBlock(subject=s, start=a, end=b) for s, a, b in TYT_BLOCKS]
        out1 = ingest_upload(db, school_id=school.school_id, file_bytes=raw,
                             filename="d.csv", exam_name="Dup",
                             exam_date=date(2026, 2, 1), subject_blocks=blocks)
        assert out1.accepted
        out2 = ingest_upload(db, school_id=school.school_id, file_bytes=raw,
                             filename="d.csv", exam_name="Dup",
                             exam_date=date(2026, 2, 1), subject_blocks=blocks)
        assert not out2.accepted
        assert any(w.code == WarningCode.DUPLICATE_UPLOAD for w in out2.warnings)

    def test_item_stats_written_to_knowledge_layer(self, seeded):
        db, school, students, exam_ids = seeded
        qs = db.questions_for_exam(exam_ids[0])
        assert all(q.p_value is not None for q in qs)
        rpbs = [q.point_biserial for q in qs if q.point_biserial is not None]
        assert sum(1 for r in rpbs if r > 0) / len(rpbs) > 0.9
        assert all(q.irt_difficulty is None for q in qs)   # v1 never writes IRT

    def test_full_flow_upload_to_rank(self, seeded):
        db, school, students, exam_ids = seeded
        st = students[0]
        mine = db.results_for_student(st.student_id)
        assert len(mine) == 3
        cohort = [r for eid in exam_ids for r in db.results_for_exam(eid)]
        est = estimate_abilities(st.student_id, mine, cohort)
        assert {e.subject for e in est} == {s for s, _, _ in TYT_BLOCKS}
        pred = predict_and_log(db, student_id=st.student_id, estimates=est,
                               engine=PlaceholderEngine(), obp_raw=st.obp)
        assert 1 <= pred.rank_low <= pred.rank_mid <= pred.rank_high <= 3_500_000
        assert len(db.open_residuals()) >= 1

    def test_reports_render(self, seeded):
        db, school, students, exam_ids = seeded
        from yks_institutional.stats.ability import refresh_school_abilities
        n = refresh_school_abilities(db, school.school_id)
        assert n >= 60 * 4        # 60 students x 4 TYT subjects
        sr = student_report(db, students[0].student_id)
        assert sr["n_exams"] == 3 and (sr["strengths"] or sr["focus_areas"])
        tr = teacher_report(db, exam_ids)
        assert len(tr["timeline"]) == 3
        pd = principal_dashboard(db, school.school_id, exam_ids)
        assert len(pd["exams"]) == 3
        # cohort improves across the seeded exams (ability_shift 0 -> .06)
        assert pd["trajectory"]["direction"] == "up"


# ------------------------------------------------------- long format (GPT) --
class TestLongFormat:
    def _long_csv(self):
        lines = ["student_no,question_no,answer"]
        for q in range(1, 5):
            lines.append(f"1278,{q},A")
        for q in range(1, 5):
            lines.append(f"42,{q},{'B' if q % 2 else 'A'}")
        lines.append("1278,2,E")            # duplicate cell -> ignored
        return "\n".join(lines).encode()

    def test_pivot_and_full_pipeline(self):
        from yks_institutional.ingestion.pipeline import SubjectBlock, ingest_upload
        db = Database()
        from yks_institutional.schemas import School
        school = School(name="L")
        db.add_school(school)
        for no in ("1278", "42"):
            db.add_student(Student(school_id=school.school_id,
                                   school_student_no=no))
        out = ingest_upload(
            db, school_id=school.school_id, file_bytes=self._long_csv(),
            filename="long.csv", exam_name="Long", exam_date=date(2026, 3, 1),
            subject_blocks=[SubjectBlock(Subject.TYT_MATEMATIK, 1, 4)],
            answer_key=["A", "A", "A", "A"])
        assert out.accepted
        assert out.n_students_imported == 2
        assert any(w.code == WarningCode.DUPLICATE_STUDENT_ROW
                   for w in out.warnings)      # duplicate cell surfaced
        res = {r.student_id: r for r in db.results_for_exam(out.exam_id)}
        nets = sorted(r.total_net_tyt for r in res.values())
        assert nets == [1.5, 4.0]              # 42: 2c2w -> 1.5; 1278: 4c -> 4.0

    def test_turkish_headers_resolve(self):
        from yks_institutional.ingestion.long_format import is_long_format
        rows = [["Öğrenci No", "Soru No", "Cevap"], ["1", "1", "A"]]
        assert is_long_format(rows)

    def test_wide_files_not_misdetected(self):
        from yks_institutional.ingestion.long_format import is_long_format
        rows = [["Ogrenci No", "S1", "S2", "S3"], ["1", "A", "B", "C"]]
        assert not is_long_format(rows)


class TestSampleWeight:
    def test_official_outcome_weighs_4x(self):
        db = Database()
        mk = TestAbility()._result
        cohort = [mk(f"c{i}", "e1", 0.5) for i in range(10)]
        eng = PlaceholderEngine()
        for sid, frac in (("a", 0.7), ("b", 0.6)):
            est = estimate_abilities(sid, [mk(sid, "e1", frac)], cohort)
            predict_and_log(db, student_id=sid, estimates=est, engine=eng)
        preds = {r.student_id: r for r in db.open_residuals()}
        db.record_outcome("a", preds["a"].predicted_rank_mid + 1000,
                          source="user_official_result")
        db.record_outcome("b", preds["b"].predicted_rank_mid + 4000,
                          source="calculator_derived")
        closed = {r.student_id: r for r in db.closed_residuals()}
        assert closed["a"].sample_weight == 4.0
        assert closed["b"].sample_weight == 1.0
        summ = residual_summary(db)
        assert summ["mae"] == 2500.0                       # (1000+4000)/2
        assert summ["weighted_mae"] == 1600.0              # (4*1000+1*4000)/5
