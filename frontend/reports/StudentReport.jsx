import React, { useMemo } from "react";

const DEFAULT_STUDENT_REPORT = {
  student_id: "8e7e362a-12fb-4f14-a619-00ea54c49e80",
  n_exams: 3,
  exams: [
    {
      exam_id: "b6be4ff5-1f08-4db2-80c5-5f5c33bf0d7b",
      tyt_net: 44.25,
      ayt_net: 0.0,
      subjects: [
        { subject: "TYT Türkçe", net: 24.5, correct: 28, wrong: 14, blank: 0 },
        { subject: "TYT Matematik", net: 10.75, correct: 15, wrong: 17, blank: 8 },
        { subject: "TYT Sosyal", net: 6.25, correct: 8, wrong: 7, blank: 5 },
        { subject: "TYT Fen", net: 2.75, correct: 5, wrong: 9, blank: 6 },
      ],
    },
    {
      exam_id: "a27bdd35-bcdc-42cb-870d-30dc76305ef4",
      tyt_net: 51.0,
      ayt_net: 14.75,
      subjects: [
        { subject: "TYT Türkçe", net: 27.0, correct: 30, wrong: 12, blank: 0 },
        { subject: "TYT Matematik", net: 13.5, correct: 18, wrong: 18, blank: 4 },
        { subject: "TYT Sosyal", net: 6.75, correct: 9, wrong: 9, blank: 2 },
        { subject: "TYT Fen", net: 3.75, correct: 6, wrong: 9, blank: 5 },
        { subject: "AYT Matematik", net: 10.5, correct: 14, wrong: 14, blank: 12 },
        { subject: "AYT Fizik", net: 1.75, correct: 3, wrong: 5, blank: 6 },
        { subject: "AYT Kimya", net: 1.5, correct: 3, wrong: 6, blank: 4 },
        { subject: "AYT Biyoloji", net: 1.0, correct: 2, wrong: 4, blank: 7 },
      ],
    },
    {
      exam_id: "5eea5221-94c8-4093-8648-6c9cc4f268bf",
      tyt_net: 57.5,
      ayt_net: 22.25,
      subjects: [
        { subject: "TYT Türkçe", net: 29.0, correct: 32, wrong: 12, blank: 0 },
        { subject: "TYT Matematik", net: 16.5, correct: 21, wrong: 18, blank: 1 },
        { subject: "TYT Sosyal", net: 7.25, correct: 10, wrong: 11, blank: 0 },
        { subject: "TYT Fen", net: 4.75, correct: 7, wrong: 9, blank: 4 },
        { subject: "AYT Matematik", net: 15.25, correct: 19, wrong: 15, blank: 6 },
        { subject: "AYT Fizik", net: 2.75, correct: 4, wrong: 5, blank: 5 },
        { subject: "AYT Kimya", net: 2.5, correct: 4, wrong: 6, blank: 3 },
        { subject: "AYT Biyoloji", net: 1.75, correct: 3, wrong: 5, blank: 5 },
      ],
    },
  ],
  strengths: [
    { subject: "TYT Türkçe", level: 61, class_average: 48, based_on_exams: 3 },
    { subject: "TYT Matematik", level: 55, class_average: 46, based_on_exams: 3 },
  ],
  focus_areas: [
    { subject: "TYT Fen", level: 34, class_average: 45, based_on_exams: 3 },
    { subject: "AYT Fizik", level: 31, class_average: 42, based_on_exams: 2 },
  ],
};

const DEFAULT_RANK_PREDICTION = {
  score_type: "SAY",
  rank_low: 95000,
  rank_mid: 110000,
  rank_high: 130000,
  flags: ["obp_missing_estimate_incomplete"],
};

// Flags are typed: "warning" flags mean the estimate is incomplete;
// "info" flags are notices about handled inputs — never alarming.
const FLAG_META = {
  obp_missing_estimate_incomplete: {
    kind: "warning",
    title: "Sonuç görünümü tamamlanmadı",
    message:
      "OBP bilgisi eksik olduğu için sıralama görünümü tamamlanmadı. OBP eklendiğinde sonuç aralığı güncellenecek.",
  },
  obp_autoconverted_from_diploma_note: {
    kind: "info",
    title: "OBP diploma notundan hesaplandı",
    message:
      "Girilen değer diploma notu olarak algılandı ve OBP'ye çevrildi. Resmi OBP değerin farklıysa güncelleyebilirsin.",
  },
};
const UNKNOWN_FLAG = {
  kind: "warning",
  title: "Sonuç görünümü tamamlanmadı",
  message:
    "Bazı bilgiler eksik olduğu için bu rapor mevcut sonuçlarla hazırlanmıştır.",
};
const isIncompleteFlag = (flag) => (FLAG_META[flag] || UNKNOWN_FLAG).kind === "warning";

const formatNumber = (value) =>
  new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 }).format(value);

const formatRank = (value) =>
  new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 }).format(value);

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

function SectionTitle({ eyebrow, title, description }) {
  return (
    <div className="mb-4">
      {eyebrow ? (
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          {eyebrow}
        </p>
      ) : null}
      <h2 className="mt-1 text-xl font-bold tracking-tight text-slate-900">
        {title}
      </h2>
      {description ? (
        <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
          {description}
        </p>
      ) : null}
    </div>
  );
}

const examHasAyt = (exam) =>
  (exam.subjects || []).some((s) => s.subject && s.subject.startsWith("AYT"));

function ProgressionChart({ exams }) {
  const width = 760;
  const height = 220;
  const padding = { top: 22, right: 28, bottom: 42, left: 42 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  const maxValue = Math.max(
    80,
    ...exams.flatMap((exam) => [exam.tyt_net || 0, exam.ayt_net || 0])
  );

  const xFor = (index) => {
    if (exams.length <= 1) return padding.left + innerWidth / 2;
    return padding.left + (index / (exams.length - 1)) * innerWidth;
  };

  const yFor = (value) =>
    padding.top + innerHeight - (clamp(value, 0, maxValue) / maxValue) * innerHeight;

  // AYT segments only span exams that actually included AYT sections —
  // a TYT-only mock must not be drawn as an AYT score of zero.
  const makePath = (key) => {
    const include = (exam) => key !== "ayt_net" || examHasAyt(exam);
    let path = "";
    let penDown = false;
    exams.forEach((exam, index) => {
      if (!include(exam)) {
        penDown = false;
        return;
      }
      const x = xFor(index);
      const y = yFor(exam[key] || 0);
      path += `${penDown ? "L" : "M"} ${x} ${y} `;
      penDown = true;
    });
    return path.trim();
  };

  const gridValues = [0, 0.25, 0.5, 0.75, 1].map((ratio) =>
    Math.round(maxValue * ratio)
  );

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-slate-900">Net gelişimi</p>
          <p className="text-sm text-slate-500">Denemeler soldan sağa ilerler.</p>
        </div>
        <div className="flex items-center gap-4 text-xs font-medium text-slate-600">
          <span className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-slate-900" />
            TYT
          </span>
          <span className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-slate-400" />
            AYT
          </span>
        </div>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="TYT ve AYT netlerinin denemelere göre gelişimi"
        className="h-auto w-full"
      >
        {gridValues.map((value) => {
          const y = yFor(value);
          return (
            <g key={value}>
              <line
                x1={padding.left}
                x2={width - padding.right}
                y1={y}
                y2={y}
                stroke="currentColor"
                className="text-slate-200"
                strokeWidth="1"
              />
              <text
                x={padding.left - 10}
                y={y + 4}
                textAnchor="end"
                className="fill-slate-400 text-xs"
              >
                {value}
              </text>
            </g>
          );
        })}

        <path
          d={makePath("tyt_net")}
          fill="none"
          stroke="currentColor"
          className="text-slate-900"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d={makePath("ayt_net")}
          fill="none"
          stroke="currentColor"
          className="text-slate-400"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {exams.map((exam, index) => (
          <g key={exam.exam_id}>
            <circle
              cx={xFor(index)}
              cy={yFor(exam.tyt_net || 0)}
              r="5"
              fill="currentColor"
              className="text-slate-900"
            />
            {examHasAyt(exam) ? (
              <circle
                cx={xFor(index)}
                cy={yFor(exam.ayt_net || 0)}
                r="5"
                fill="currentColor"
                className="text-slate-400"
              />
            ) : null}
            <text
              x={xFor(index)}
              y={height - 14}
              textAnchor="middle"
              className="fill-slate-500 text-xs"
            >
              Deneme {index + 1}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function RankSummary({ prediction, placementOutlook }) {
  // Only warning-kind flags make the estimate incomplete; info flags do not.
  const isIncomplete = prediction.flags.some(isIncompleteFlag);
  // Placement band comes ONLY from the placement engine. Until that payload
  // exists (contract v1.2 request), show a neutral preparing state — never a
  // hardcoded verdict.
  const bandLabel = isIncomplete
    ? "Bilgi bekleniyor"
    : placementOutlook || "Hazırlanıyor";

  return (
    <section className="break-inside-avoid rounded-3xl bg-slate-900 p-6 text-white shadow-lg print:rounded-xl print:p-5 print:shadow-none">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-300">
            {prediction.score_type} sıralama görünümü
          </p>
          <p className="mt-3 text-2xl font-bold leading-tight sm:text-3xl">
            Sıralaman büyük olasılıkla{" "}
            <span className="whitespace-nowrap">
              {formatRank(prediction.rank_low)} – {formatRank(prediction.rank_high)}
            </span>{" "}
            arasında.
          </p>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
            Orta nokta yaklaşık {formatRank(prediction.rank_mid)}. Sıralamada daha
            küçük sayı daha iyi sonucu gösterir.
          </p>
        </div>

        <div className="rounded-2xl bg-white/10 p-4" style={{ minWidth: 220 }}>
          <p className="text-xs uppercase tracking-widest text-slate-300">
            Yerleşme görünümü
          </p>
          <p className="mt-2 text-xl font-bold">{bandLabel}</p>
          <p className="mt-1 text-sm leading-5 text-slate-300">
            Bölüm seçenekleri kesin sonuç anlamına gelmez.
          </p>
        </div>
      </div>
    </section>
  );
}

function WarningBanners({ flags }) {
  if (!flags.length) return null;

  return (
    <div className="space-y-3" aria-live="polite">
      {flags.map((flag) => {
        const meta = FLAG_META[flag] || UNKNOWN_FLAG;
        const warning = meta.kind === "warning";
        return (
          <div
            key={flag}
            className={`break-inside-avoid rounded-2xl border px-4 py-3 ${
              warning
                ? "border-amber-300 bg-amber-50 text-amber-900"
                : "border-sky-300 bg-sky-50 text-sky-900"
            }`}
          >
            <p className="font-semibold">{meta.title}</p>
            <p className="mt-1 text-sm leading-6">{meta.message}</p>
          </div>
        );
      })}
    </div>
  );
}

function SubjectTable({ exam, examIndex }) {
  return (
    <article className="break-inside-avoid rounded-2xl border border-slate-200 bg-white shadow-sm print:shadow-none">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
        <div>
          <h3 className="font-bold text-slate-900">Deneme {examIndex + 1}</h3>
          <p className="text-xs text-slate-500">
            TYT {formatNumber(exam.tyt_net)} net · AYT {formatNumber(exam.ayt_net)} net
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
          {exam.subjects.length} ders
        </span>
      </div>

      <div className="overflow-x-auto print:overflow-visible">
        <table className="w-full border-collapse text-left text-sm" style={{ minWidth: 620 }}>
          <thead>
            <tr className="text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3 font-semibold">Ders</th>
              <th className="px-4 py-3 text-right font-semibold">Net</th>
              <th className="px-4 py-3 text-right font-semibold">Doğru</th>
              <th className="px-4 py-3 text-right font-semibold">Yanlış</th>
              <th className="px-4 py-3 text-right font-semibold">Boş</th>
            </tr>
          </thead>
          <tbody>
            {exam.subjects.map((subject) => (
              <tr
                key={`${exam.exam_id}-${subject.subject}`}
                className="border-t border-slate-100"
              >
                <td className="px-4 py-3 font-medium text-slate-900">
                  {subject.subject}
                </td>
                <td className="px-4 py-3 text-right font-bold text-slate-900">
                  {formatNumber(subject.net)}
                </td>
                <td className="px-4 py-3 text-right text-slate-600">
                  {subject.correct}
                </td>
                <td className="px-4 py-3 text-right text-slate-600">
                  {subject.wrong}
                </td>
                <td className="px-4 py-3 text-right text-slate-600">
                  {subject.blank}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function LevelCard({ item, type }) {
  const difference = item.level - item.class_average;
  const isStrength = type === "strength";

  return (
    <article className="break-inside-avoid rounded-2xl border border-slate-200 bg-white p-4 shadow-sm print:shadow-none">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-bold text-slate-900">{item.subject}</p>
          <p className="mt-1 text-xs text-slate-500">
            {item.based_on_exams} denemeye göre
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            isStrength
              ? "bg-emerald-100 text-emerald-800"
              : "bg-rose-100 text-rose-800"
          }`}
        >
          {isStrength ? "Güçlü alan" : "Odak alanı"}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-slate-50 p-3">
          <p className="text-xs text-slate-500">Seviye</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">{item.level}</p>
        </div>
        <div className="rounded-xl bg-slate-50 p-3">
          <p className="text-xs text-slate-500">Sınıf ortalaması</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">
            {item.class_average}
          </p>
        </div>
      </div>

      <div className="mt-4">
        <div className="h-2 overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-slate-900"
            style={{ width: `${clamp(item.level, 0, 100)}%` }}
          />
        </div>
        <p className="mt-2 text-sm leading-5 text-slate-600">
          {difference >= 0
            ? `Sınıf ortalamasının ${difference} puan üzerinde.`
            : `Sınıf ortalamasının ${Math.abs(difference)} puan altında.`}
        </p>
      </div>
    </article>
  );
}

function PrintStyles() {
  return (
    <style>{`
      @page {
        size: A4;
        margin: 12mm;
      }

      @media print {
        html,
        body {
          background: white !important;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }

        body {
          margin: 0;
        }

        .student-report-shell {
          width: 100%;
          max-width: none !important;
          padding: 0 !important;
        }

        .screen-only {
          display: none !important;
        }

        .print-page-break {
          break-before: page;
          page-break-before: always;
        }

        section,
        article,
        table,
        svg {
          break-inside: avoid;
          page-break-inside: avoid;
        }

        table {
          font-size: 10px;
        }

        th,
        td {
          padding-top: 5px !important;
          padding-bottom: 5px !important;
        }

        h1 {
          font-size: 22px !important;
        }

        h2 {
          font-size: 16px !important;
        }

        p {
          orphans: 3;
          widows: 3;
        }
      }
    `}</style>
  );
}

export default function StudentReport({
  studentReport = DEFAULT_STUDENT_REPORT,
  rankPrediction = DEFAULT_RANK_PREDICTION,
  placementOutlook = null, // e.g. "Güçlü ihtimal" | "Dengede" | "Zorlu" — from placement engine only
}) {
  const latestExam = studentReport.exams[studentReport.exams.length - 1];

  const progression = useMemo(() => {
    if (studentReport.exams.length < 2) return null;
    const first = studentReport.exams[0];
    const firstWithAyt = studentReport.exams.find(examHasAyt);
    return {
      tyt: latestExam.tyt_net - first.tyt_net,
      ayt:
        firstWithAyt && examHasAyt(latestExam) && firstWithAyt !== latestExam
          ? latestExam.ayt_net - firstWithAyt.ayt_net
          : null,
    };
  }, [studentReport.exams, latestExam]);

  return (
    <>
      <PrintStyles />

      <main className="min-h-screen bg-slate-100 px-4 py-8 text-slate-900 sm:px-6 lg:px-8 print:min-h-0 print:bg-white print:p-0">
        <div className="student-report-shell mx-auto max-w-6xl space-y-6">
          <header className="break-inside-avoid rounded-3xl border border-slate-200 bg-white p-6 shadow-sm print:rounded-xl print:shadow-none">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
                  YKS Radar öğrenci raporu
                </p>
                <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
                  Deneme gelişim özeti
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
                  Bu rapor, son {studentReport.n_exams} denemedeki netlerini, ders
                  görünümünü ve çalışma önceliklerini bir arada gösterir.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div className="rounded-2xl bg-slate-900 px-4 py-3 text-white">
                  <p className="text-xs text-slate-300">Son TYT neti</p>
                  <p className="mt-1 text-2xl font-bold">
                    {formatNumber(latestExam.tyt_net)}
                  </p>
                </div>
                <div className="rounded-2xl bg-slate-200 px-4 py-3">
                  <p className="text-xs text-slate-500">Son AYT neti</p>
                  <p className="mt-1 text-2xl font-bold text-slate-900">
                    {examHasAyt(latestExam) ? formatNumber(latestExam.ayt_net) : "—"}
                  </p>
                </div>
                <div className="col-span-2 rounded-2xl border border-slate-200 px-4 py-3 sm:col-span-1">
                  <p className="text-xs text-slate-500">Toplam deneme</p>
                  <p className="mt-1 text-2xl font-bold text-slate-900">
                    {studentReport.n_exams}
                  </p>
                </div>
              </div>
            </div>
          </header>

          <WarningBanners flags={rankPrediction.flags} />

          <RankSummary prediction={rankPrediction} placementOutlook={placementOutlook} />

          <section className="break-inside-avoid rounded-3xl border border-slate-200 bg-white p-6 shadow-sm print:rounded-xl print:shadow-none">
            <SectionTitle
              eyebrow="Gelişim"
              title="Denemeden denemeye net değişimi"
              description="TYT ve AYT netlerinin son denemelerde nasıl ilerlediğini gösterir."
            />

            <ProgressionChart exams={studentReport.exams} />

            {progression ? (
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">İlk denemeden beri TYT</p>
                  <p className="mt-1 text-xl font-bold text-slate-900">
                    {progression.tyt >= 0 ? "+" : ""}
                    {formatNumber(progression.tyt)} net
                  </p>
                </div>
                {progression.ayt !== null ? (
                  <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-xs text-slate-500">
                      İlk AYT denemesinden beri
                    </p>
                    <p className="mt-1 text-xl font-bold text-slate-900">
                      {progression.ayt >= 0 ? "+" : ""}
                      {formatNumber(progression.ayt)} net
                    </p>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>

          <section className="print-page-break">
            <SectionTitle
              eyebrow="Ders görünümü"
              title="Her denemenin ders bazında sonucu"
              description="Doğru, yanlış ve boş sayılarıyla birlikte netlerini karşılaştır."
            />
            <div className="grid gap-4">
              {studentReport.exams.map((exam, index) => (
                <SubjectTable key={exam.exam_id} exam={exam} examIndex={index} />
              ))}
            </div>
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <div>
              <SectionTitle
                eyebrow="Güçlü taraflar"
                title="Öne çıkan dersler"
                description="Mevcut denemelerde sınıf ortalamasının üzerinde kalan alanlar."
              />
              <div className="grid gap-4">
                {studentReport.strengths.map((item) => (
                  <LevelCard key={item.subject} item={item} type="strength" />
                ))}
              </div>
            </div>

            <div>
              <SectionTitle
                eyebrow="Çalışma önceliği"
                title="Odaklanılması gereken alanlar"
                description="Düzenli tekrar ve soru çözümüyle en hızlı gelişim sağlanabilecek dersler."
              />
              <div className="grid gap-4">
                {studentReport.focus_areas.map((item) => (
                  <LevelCard key={item.subject} item={item} type="focus" />
                ))}
              </div>
            </div>
          </section>

          <footer className="break-inside-avoid rounded-2xl border border-slate-200 bg-white px-5 py-4 text-xs leading-5 text-slate-500">
            Bu rapor kesin yerleşme sonucu vermez. Deneme performansı, OBP ve sınav
            günündeki sonuçlar değişebilir. Bölüm tercihleri yapılırken güncel
            kontenjanlar ve resmi yerleştirme sonuçları ayrıca değerlendirilmelidir.
          </footer>
        </div>
      </main>
    </>
  );
}
