import React, { useMemo } from "react";

const DEFAULT_PRINCIPAL_DASHBOARD = {
  school_id: "1a4722d4-96f7-4f72-a30f-57ca491a9379",
  as_of: "2026-07-21",
  exams: [
    {
      exam_id: "6fa70c31-f44d-47a4-af51-247db9f5be1d",
      n_students: 18,
      tyt_net_mean: 34.6,
      tyt_net_median: 34.0,
      tyt_net_p25: 18.8,
      tyt_net_p75: 51.2,
    },
    {
      exam_id: "48040cb1-bb46-4a1e-9fc7-f18d55649bd7",
      n_students: 176,
      tyt_net_mean: 40.9,
      tyt_net_median: 40.1,
      tyt_net_p25: 25.5,
      tyt_net_p75: 56.4,
    },
    {
      exam_id: "b464ea25-d59f-414e-82ea-e8015e450446",
      n_students: 200,
      tyt_net_mean: 47.9,
      tyt_net_median: 47.3,
      tyt_net_p25: 31.8,
      tyt_net_p75: 63.1,
    },
  ],
  trajectory: {
    tyt_net_change: 13.3,
    direction: "up",
  },
};

const FLAG_META = {
  small_group: {
    kind: "warning",
    label: "Katılım sınırlı",
    title: "Bu denemeyi dikkatle karşılaştırın",
    description:
      "Katılan öğrenci sayısı düşük olduğunda okul geneli görünümü daha hızlı değişebilir.",
  },
  trajectory_missing: {
    kind: "info",
    label: "Gelişim bekleniyor",
    title: "Henüz karşılaştırma yapılamıyor",
    description:
      "Okulun yönünü göstermek için en az iki deneme sonucu gerekir.",
  },
  trajectory_unknown: {
    kind: "info",
    label: "Yön belirtilmedi",
    title: "Gelişim yönü gösterilemiyor",
    description:
      "Gelen veride gelişim yönü bulunmadığı için yalnızca deneme sonuçları gösteriliyor.",
  },
};

const KIND_STYLES = {
  warning: {
    card: "border-amber-300 bg-amber-50",
    badge: "bg-amber-100 text-amber-900",
    text: "text-amber-900",
  },
  info: {
    card: "border-sky-200 bg-sky-50",
    badge: "bg-sky-100 text-sky-900",
    text: "text-sky-900",
  },
};

const DIRECTION_META = {
  up: {
    arrow: "↑",
    label: "Yükseliyor",
    detail: "TYT netleri önceki denemelere göre arttı.",
    badge: "bg-emerald-100 text-emerald-900",
  },
  down: {
    arrow: "↓",
    label: "Geriliyor",
    detail: "TYT netleri önceki denemelere göre düştü.",
    badge: "bg-rose-100 text-rose-900",
  },
  flat: {
    arrow: "→",
    label: "Benzer düzeyde",
    detail: "TYT netleri önceki denemelere yakın seyrediyor.",
    badge: "bg-slate-200 text-slate-900",
  },
};

const SMALL_GROUP_LIMIT = 30;

const isNumber = (value) =>
  typeof value === "number" && Number.isFinite(value);

const formatNumber = (value) =>
  isNumber(value)
    ? new Intl.NumberFormat("tr-TR", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      }).format(value)
    : "Veri yok";

const formatInteger = (value) =>
  isNumber(value)
    ? new Intl.NumberFormat("tr-TR", {
        maximumFractionDigits: 0,
      }).format(value)
    : "Veri yok";

const formatDate = (value) => {
  if (typeof value !== "string" || !value) return "Tarih yok";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "Tarih yok";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
};

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

function SectionTitle({ eyebrow, title, description }) {
  return (
    <div className="mb-4">
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
        {eyebrow}
      </p>
      <h2 className="mt-1 text-xl font-bold tracking-tight text-slate-900">
        {title}
      </h2>
      <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
        {description}
      </p>
    </div>
  );
}

function StatusBanner({ flagName }) {
  const meta = FLAG_META[flagName] || {
    kind: "info",
    label: "Bilgi",
    title: "Ek bilgi bulunuyor",
    description: "Bu bölüm mevcut verilerle gösteriliyor.",
  };
  const styles = KIND_STYLES[meta.kind] || KIND_STYLES.info;

  return (
    <div
      className={`rounded-2xl border px-4 py-4 ${styles.card}`}
      role="status"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className={`font-bold ${styles.text}`}>{meta.title}</p>
          <p className="mt-1 text-sm leading-6 text-slate-700">
            {meta.description}
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${styles.badge}`}
        >
          {meta.label}
        </span>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, detail }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm print:shadow-none">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-3xl font-bold tracking-tight text-slate-900">
        {value}
      </p>
      <p className="mt-1 text-sm leading-5 text-slate-600">{detail}</p>
    </article>
  );
}

function TrajectoryCard({ trajectory }) {
  if (!trajectory) {
    return <StatusBanner flagName="trajectory_missing" />;
  }

  const direction =
    typeof trajectory.direction === "string"
      ? DIRECTION_META[trajectory.direction]
      : null;

  if (!direction) {
    return <StatusBanner flagName="trajectory_unknown" />;
  }

  const change = trajectory.tyt_net_change;
  const changeText = isNumber(change)
    ? `${change > 0 ? "+" : ""}${formatNumber(change)} net`
    : "Değişim bilgisi yok";

  return (
    <article className="rounded-3xl print:rounded-xl bg-slate-900 p-6 text-white shadow-lg print:shadow-none">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-300">
            Okulun TYT yönü
          </p>
          <div className="mt-3 flex items-center gap-3">
            <span className="text-4xl font-bold" aria-hidden="true">
              {direction.arrow}
            </span>
            <div>
              <p className="text-2xl font-bold">{direction.label}</p>
              <p className="mt-1 text-sm leading-6 text-slate-300">
                {direction.detail}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-2xl bg-slate-800 px-5 py-4">
          <p className="text-xs text-slate-300">Net değişimi</p>
          <p className="mt-1 text-2xl font-bold">{changeText}</p>
        </div>
      </div>
    </article>
  );
}

function DistributionChart({ exams }) {
  const width = 900;
  const height = 330;
  const padding = { top: 25, right: 30, bottom: 55, left: 48 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const validValues = exams.flatMap((exam) =>
    [
      exam?.tyt_net_mean,
      exam?.tyt_net_median,
      exam?.tyt_net_p25,
      exam?.tyt_net_p75,
    ].filter(isNumber)
  );
  const maxValue = Math.max(80, ...validValues);
  const columnWidth = exams.length
    ? innerWidth / exams.length
    : innerWidth;

  const yFor = (value) =>
    padding.top +
    innerHeight -
    (clamp(value, 0, maxValue) / maxValue) * innerHeight;

  const gridValues = [0, 0.25, 0.5, 0.75, 1].map((part) =>
    Math.round(maxValue * part)
  );

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm print:shadow-none">
      <div className="mb-4">
        <p className="font-semibold text-slate-900">TYT net dağılımı</p>
        <p className="mt-1 text-sm text-slate-500">
          Koyu nokta ortalamayı, açık nokta ortanca değeri gösterir. Dikey çizgi,
          öğrencilerin orta bölümünün bulunduğu alanı gösterir.
        </p>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Denemelere göre okul TYT net dağılımı"
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
                stroke="#e2e8f0"
                strokeWidth="1"
              />
              <text
                x={padding.left - 10}
                y={y + 4}
                textAnchor="end"
                fill="#64748b"
                fontSize="11"
              >
                {value}
              </text>
            </g>
          );
        })}

        {exams.map((exam, index) => {
          const safeExam = exam || {};
          const x =
            padding.left + columnWidth * index + columnWidth / 2;
          const p25 = safeExam.tyt_net_p25;
          const p75 = safeExam.tyt_net_p75;
          const mean = safeExam.tyt_net_mean;
          const median = safeExam.tyt_net_median;
          const hasBand = isNumber(p25) && isNumber(p75);
          const hasMean = isNumber(mean);
          const hasMedian = isNumber(median);

          return (
            <g key={safeExam.exam_id || `exam-${index}`}>
              {hasBand ? (
                <>
                  <line
                    x1={x}
                    x2={x}
                    y1={yFor(p75)}
                    y2={yFor(p25)}
                    stroke="#94a3b8"
                    strokeWidth="8"
                    strokeLinecap="round"
                  />
                  <line
                    x1={x - 10}
                    x2={x + 10}
                    y1={yFor(p75)}
                    y2={yFor(p75)}
                    stroke="#64748b"
                    strokeWidth="2"
                  />
                  <line
                    x1={x - 10}
                    x2={x + 10}
                    y1={yFor(p25)}
                    y2={yFor(p25)}
                    stroke="#64748b"
                    strokeWidth="2"
                  />
                </>
              ) : null}

              {hasMean ? (
                <circle cx={x - 7} cy={yFor(mean)} r="6" fill="#0f172a">
                  <title>{`Deneme ${index + 1}: ortalama ${formatNumber(mean)}`}</title>
                </circle>
              ) : null}

              {hasMedian ? (
                <circle cx={x + 7} cy={yFor(median)} r="6" fill="#cbd5e1">
                  <title>{`Deneme ${index + 1}: ortanca ${formatNumber(median)}`}</title>
                </circle>
              ) : null}

              {!hasBand && !hasMean && !hasMedian ? (
                <text
                  x={x}
                  y={padding.top + innerHeight / 2}
                  textAnchor="middle"
                  fill="#94a3b8"
                  fontSize="12"
                >
                  Veri yok
                </text>
              ) : null}

              <text
                x={x}
                y={height - 18}
                textAnchor="middle"
                fill="#64748b"
                fontSize="12"
              >
                Deneme {index + 1}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function ExamCard({ exam, index }) {
  const safeExam = exam || {};
  const studentCount = safeExam.n_students;
  const isSmallGroup =
    isNumber(studentCount) &&
    studentCount > 0 &&
    studentCount < SMALL_GROUP_LIMIT;

  const metrics = [
    { label: "Ortalama", value: safeExam.tyt_net_mean },
    { label: "Ortanca", value: safeExam.tyt_net_median },
    { label: "Alt bölüm", value: safeExam.tyt_net_p25 },
    { label: "Üst bölüm", value: safeExam.tyt_net_p75 },
  ];

  return (
    <article className="rounded-2xl border border-slate-200 bg-white shadow-sm print:shadow-none">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div>
          <h3 className="font-bold text-slate-900">Deneme {index + 1}</h3>
          <p className="mt-1 text-sm text-slate-500">
            {isNumber(studentCount)
              ? `${formatInteger(studentCount)} öğrenci`
              : "Öğrenci sayısı yok"}
          </p>
        </div>

        {isSmallGroup ? (
          <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900">
            Katılım sınırlı
          </span>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-px bg-slate-200">
        {metrics.map((metric) => (
          <div key={metric.label} className="bg-white p-4">
            <p className="text-xs text-slate-500">{metric.label}</p>
            <p className="mt-1 text-xl font-bold text-slate-900">
              {formatNumber(metric.value)}
            </p>
          </div>
        ))}
      </div>

      {isSmallGroup ? (
        <div className="border-t border-amber-200 bg-amber-50 px-5 py-3">
          <p className="text-xs leading-5 text-amber-900">
            Bu denemenin katılımı diğer sonuçlarla karşılaştırılırken dikkatle
            değerlendirilmelidir.
          </p>
        </div>
      ) : null}
    </article>
  );
}

function EmptyState({ title, description }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="font-bold text-slate-900">{title}</p>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-600">
        {description}
      </p>
    </div>
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

        .report-shell {
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

export default function PrincipalDashboard({
  principalDashboard = DEFAULT_PRINCIPAL_DASHBOARD,
}) {
  const exams = Array.isArray(principalDashboard?.exams)
    ? principalDashboard.exams
    : [];

  const latestExam = exams.length ? exams[exams.length - 1] || {} : null;

  const totalStudents = useMemo(() => {
    const counts = exams
      .map((exam) => exam?.n_students)
      .filter(isNumber);
    return counts.length ? Math.max(...counts) : null;
  }, [exams]);

  const smallGroupCount = useMemo(
    () =>
      exams.filter(
        (exam) =>
          isNumber(exam?.n_students) &&
          exam.n_students > 0 &&
          exam.n_students < SMALL_GROUP_LIMIT
      ).length,
    [exams]
  );

  const latestMean = latestExam?.tyt_net_mean;
  const latestMedian = latestExam?.tyt_net_median;

  return (
    <>
      <PrintStyles />

      <main className="min-h-screen bg-slate-100 px-4 py-8 text-slate-900 sm:px-6 lg:px-8 print:min-h-0 print:bg-white print:p-0">
      <div className="report-shell mx-auto max-w-7xl space-y-6">
        <header className="rounded-3xl print:rounded-xl border border-slate-200 bg-white p-6 shadow-sm print:shadow-none">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            YKS Radar yönetici görünümü
          </p>

          <div className="mt-2 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
                Okul performans özeti
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
                TYT net dağılımını, denemeler arasındaki yönü ve katılım sayılarını
                tek ekranda gösterir.
              </p>
              <p className="mt-2 text-xs text-slate-500">
                Son güncelleme: {formatDate(principalDashboard?.as_of)}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <SummaryCard
                label="Deneme sayısı"
                value={formatInteger(exams.length)}
                detail="Gösterilen sınav"
              />
              <SummaryCard
                label="Öğrenci sayısı"
                value={formatInteger(totalStudents)}
                detail="En yüksek katılım"
              />
              <div className="col-span-2 sm:col-span-1">
                <SummaryCard
                  label="Son TYT ortalaması"
                  value={formatNumber(latestMean)}
                  detail={
                    isNumber(latestMedian)
                      ? `Ortanca ${formatNumber(latestMedian)}`
                      : "Ortanca bilgisi yok"
                  }
                />
              </div>
            </div>
          </div>
        </header>

        {smallGroupCount > 0 ? (
          <StatusBanner flagName="small_group" />
        ) : null}

        <TrajectoryCard trajectory={principalDashboard?.trajectory ?? null} />

        <section>
          <SectionTitle
            eyebrow="Okul dağılımı"
            title="Denemelere göre TYT görünümü"
            description="Ortalama, ortanca ve öğrencilerin orta bölümündeki net aralığı birlikte gösterilir."
          />

          {exams.length ? (
            <DistributionChart exams={exams} />
          ) : (
            <EmptyState
              title="Henüz deneme sonucu yok"
              description="Okul sonuçları geldiğinde TYT net dağılımı burada gösterilecek."
            />
          )}
        </section>

        <section>
          <SectionTitle
            eyebrow="Deneme ayrıntıları"
            title="Katılım ve temel değerler"
            description="Her denemenin katılım sayısı ve TYT net özeti ayrı kartlarda gösterilir."
          />

          {exams.length ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {exams.map((exam, index) => (
                <ExamCard
                  key={exam?.exam_id || `exam-${index}`}
                  exam={exam}
                  index={index}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              title="Gösterilecek deneme bulunmuyor"
              description="İlk deneme yüklendiğinde ayrıntılar bu bölümde yer alacak."
            />
          )}
        </section>

        <footer className="rounded-2xl border border-slate-200 bg-white px-5 py-4 text-xs leading-5 text-slate-500">
          Bu görünüm okulun mevcut deneme sonuçlarını özetler. Eğitim planı
          oluşturulurken ders bazındaki sonuçlar, sınıf gözlemleri ve denemeye
          katılım düzeyi birlikte değerlendirilmelidir.
        </footer>
      </div>
      </main>
    </>
  );
}
