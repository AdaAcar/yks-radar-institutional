import React, { useMemo } from "react";

const DEFAULT_TEACHER_REPORT = {
  timeline: [
    {
      exam_id: "43af08e5-312a-4852-936d-efca2b424f60",
      topics: { Geometri: 51, Paragraf: 54, Problemler: 43, "TYT Fen": 38 },
    },
    {
      exam_id: "6ba27cd0-bbe1-4505-a108-e37e74657da2",
      topics: { Geometri: 47, Paragraf: 57, Problemler: 48, "TYT Fen": 41 },
    },
    {
      exam_id: "1dde569d-fe52-49e5-a9ba-451ffb70b504",
      topics: { Geometri: 42, Paragraf: 61, Problemler: 55, "TYT Fen": 46 },
    },
  ],
  trends: [
    { topic: "Geometri", change: -9, direction: "declining", from: 51, to: 42 },
    { topic: "Paragraf", change: 7, direction: "improving", from: 54, to: 61 },
    { topic: "Problemler", change: 12, direction: "improving", from: 43, to: 55 },
    { topic: "TYT Fen", change: 8, direction: "improving", from: 38, to: 46 },
  ],
};

/*
 * teacher_report has no flags field. This metadata maps only contract-backed
 * trend directions to display severity; no warning payload is invented.
 */
const FLAG_META = {
  declining: {
    kind: "warning",
    label: "Geriliyor",
    title: "Yakından izlenmeli",
    description: "Son denemelerde düşüş görülüyor.",
  },
  improving: {
    kind: "info",
    label: "Gelişiyor",
    title: "Olumlu ilerleme",
    description: "Son denemelerde yükseliş görülüyor.",
  },
};

const KIND_STYLES = {
  warning: {
    card: "border-amber-300 bg-amber-50",
    badge: "bg-amber-100 text-amber-900",
    text: "text-amber-950",
    line: "#b45309",
  },
  info: {
    card: "border-sky-200 bg-sky-50",
    badge: "bg-sky-100 text-sky-900",
    text: "text-sky-950",
    line: "#0369a1",
  },
};

const TOPIC_COLORS = ["#0f172a", "#475569", "#0284c7", "#059669", "#7c3aed", "#be123c"];
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

function allTopics(timeline) {
  const output = [];
  const seen = new Set();
  timeline.forEach((exam) => {
    Object.keys(exam.topics).forEach((topic) => {
      if (!seen.has(topic)) {
        seen.add(topic);
        output.push(topic);
      }
    });
  });
  return output;
}

function SectionTitle({ eyebrow, title, description }) {
  return (
    <div className="mb-4">
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">{eyebrow}</p>
      <h2 className="mt-1 text-xl font-bold tracking-tight text-slate-900">{title}</h2>
      <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">{description}</p>
    </div>
  );
}

function SummaryCard({ label, value, detail }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm print:shadow-none">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-bold tracking-tight text-slate-900">{value}</p>
      <p className="mt-1 text-sm leading-5 text-slate-600">{detail}</p>
    </article>
  );
}

function TimelineChart({ timeline, topics }) {
  const width = 880;
  const height = 340;
  const pad = { top: 28, right: 30, bottom: 54, left: 48 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const xFor = (index) =>
    timeline.length <= 1 ? pad.left + innerWidth / 2 : pad.left + (index / (timeline.length - 1)) * innerWidth;
  const yFor = (value) => pad.top + innerHeight - (clamp(value, 0, 100) / 100) * innerHeight;
  const pathFor = (topic) =>
    timeline
      .map((exam, index) =>
        typeof exam.topics[topic] === "number" ? { x: xFor(index), y: yFor(exam.topics[topic]) } : null
      )
      .filter(Boolean)
      .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
      .join(" ");

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm print:shadow-none">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-semibold text-slate-900">Konu gelişim çizgileri</p>
          <p className="mt-1 text-sm text-slate-500">Her çizgi, konunun denemeler boyunca 0–100 arasındaki seviyesini gösterir.</p>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          {topics.map((topic, index) => (
            <span key={topic} className="flex items-center gap-2 text-xs font-medium text-slate-600">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: TOPIC_COLORS[index % TOPIC_COLORS.length] }} />
              {topic}
            </span>
          ))}
        </div>
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Konuların denemelere göre gelişimi" className="h-auto w-full">
        {[0, 25, 50, 75, 100].map((value) => {
          const y = yFor(value);
          return (
            <g key={value}>
              <line x1={pad.left} x2={width - pad.right} y1={y} y2={y} stroke="#e2e8f0" strokeWidth="1" />
              <text x={pad.left - 10} y={y + 4} textAnchor="end" fill="#64748b" fontSize="11">{value}</text>
            </g>
          );
        })}

        {timeline.map((exam, index) => (
          <g key={exam.exam_id}>
            <line x1={xFor(index)} x2={xFor(index)} y1={pad.top} y2={height - pad.bottom} stroke="#f1f5f9" strokeWidth="1" />
            <text x={xFor(index)} y={height - 18} textAnchor="middle" fill="#64748b" fontSize="12">Deneme {index + 1}</text>
          </g>
        ))}

        {topics.map((topic, topicIndex) => {
          const color = TOPIC_COLORS[topicIndex % TOPIC_COLORS.length];
          return (
            <g key={topic}>
              <path d={pathFor(topic)} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
              {timeline.map((exam, examIndex) => {
                const value = exam.topics[topic];
                if (typeof value !== "number") return null;
                return (
                  <circle key={`${exam.exam_id}-${topic}`} cx={xFor(examIndex)} cy={yFor(value)} r="5" fill={color} stroke="white" strokeWidth="2">
                    <title>{`${topic}: Deneme ${examIndex + 1}, seviye ${value}`}</title>
                  </circle>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function LatestTopics({ timeline, topics }) {
  const latest = timeline[timeline.length - 1];
  return (
    <article className="rounded-2xl border border-slate-200 bg-white shadow-sm print:shadow-none">
      <div className="border-b border-slate-200 px-5 py-4">
        <h3 className="font-bold text-slate-900">Son deneme görünümü</h3>
        <p className="mt-1 text-sm text-slate-500">Deneme {timeline.length} içindeki konu seviyeleri</p>
      </div>
      <div className="divide-y divide-slate-100">
        {topics.map((topic) => {
          const value = latest.topics[topic];
          const hasValue = typeof value === "number";
          return (
            <div key={topic} className="grid grid-cols-3 items-center gap-4 px-5 py-4">
              <div className="col-span-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium text-slate-900">{topic}</p>
                  <p className="text-sm font-bold text-slate-900">{hasValue ? value : "—"}</p>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-slate-900"
                    style={{ width: `${hasValue ? clamp(value, 0, 100) : 0}%` }}
                  />
                </div>
              </div>
              <p className="text-right text-xs text-slate-500">
                {hasValue ? "0–100 seviye" : "Bu denemede sonuç yok"}
              </p>
            </div>
          );
        })}
      </div>
    </article>
  );
}

const UNKNOWN_TREND = {
  kind: "info",
  label: "Değişim",
  title: "Seviye değişti",
  description: "Son denemeler arasında fark görülüyor.",
};

function TrendCard({ trend }) {
  const meta = FLAG_META[trend.direction] || UNKNOWN_TREND;
  const styles = KIND_STYLES[meta.kind];
  return (
    <article className={`rounded-2xl border p-5 ${styles.card}`} aria-label={`${trend.topic}: ${meta.label}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-lg font-bold text-slate-900">{trend.topic}</p>
          <p className={`mt-1 text-sm font-semibold ${styles.text}`}>{meta.title}</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${styles.badge}`}>{meta.label}</span>
      </div>
      <div className="mt-5 grid grid-cols-3 gap-3">
        <div className="rounded-xl bg-white p-3"><p className="text-xs text-slate-500">Önce</p><p className="mt-1 text-xl font-bold text-slate-900">{trend.from}</p></div>
        <div className="rounded-xl bg-white p-3"><p className="text-xs text-slate-500">Şimdi</p><p className="mt-1 text-xl font-bold text-slate-900">{trend.to}</p></div>
        <div className="rounded-xl bg-white p-3"><p className="text-xs text-slate-500">Değişim</p><p className="mt-1 text-xl font-bold text-slate-900">{trend.change > 0 ? "+" : ""}{trend.change}</p></div>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <span aria-hidden="true" className="text-2xl font-bold" style={{ color: styles.line }}>{trend.direction === "declining" ? "↓" : trend.direction === "improving" ? "↑" : "→"}</span>
        <p className="text-sm leading-6 text-slate-700">{meta.description}</p>
      </div>
    </article>
  );
}

function EmptyState({ title, description }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="font-bold text-slate-900">{title}</p>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-600">{description}</p>
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

export default function TeacherReport({ teacherReport = DEFAULT_TEACHER_REPORT }) {
  const topics = useMemo(() => allTopics(teacherReport.timeline), [teacherReport.timeline]);
  const improving = teacherReport.trends.filter((trend) => trend.direction === "improving").length;
  const declining = teacherReport.trends.filter((trend) => trend.direction === "declining").length;

  return (
    <>
      <PrintStyles />

      <main className="min-h-screen bg-slate-100 px-4 py-8 text-slate-900 sm:px-6 lg:px-8 print:min-h-0 print:bg-white print:p-0">
      <div className="report-shell mx-auto max-w-7xl space-y-6">
        <header className="rounded-3xl print:rounded-xl border border-slate-200 bg-white p-6 shadow-sm print:shadow-none">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">YKS Radar öğretmen raporu</p>
          <div className="mt-2 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Sınıf konu gelişimi</h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">Denemeler boyunca konu seviyelerinin nasıl değiştiğini ve dikkat edilmesi gereken hareketleri bir arada gösterir.</p>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div className="col-span-2 sm:col-span-1"><SummaryCard label="Deneme sayısı" value={teacherReport.timeline.length} detail="Karşılaştırılan sınav" /></div>
              <SummaryCard label="Gelişen konu" value={improving} detail="Yükseliş gösteren" />
              <SummaryCard label="Gerileyen konu" value={declining} detail="Yakından izlenecek" />
            </div>
          </div>
        </header>

        <section>
          <SectionTitle eyebrow="Zaman içindeki değişim" title="Konu ve ders çizgileri" description="Yalnızca rapora gelen sonuçlar gösterilir. Eksik bir konu değeri tamamlanmaz veya varsayılmaz." />
          {teacherReport.timeline.length && topics.length ? <TimelineChart timeline={teacherReport.timeline} topics={topics} /> : <EmptyState title="Henüz çizilecek sonuç yok" description="Konu seviyeleri geldiğinde denemeler arasındaki değişim burada gösterilecek." />}
        </section>

        {teacherReport.timeline.length && topics.length ? (
          <section>
            <SectionTitle eyebrow="Güncel durum" title="Son denemedeki konu seviyeleri" description="Her konu 0–100 arasında, rapora geldiği biçimde gösterilir." />
            <LatestTopics timeline={teacherReport.timeline} topics={topics} />
          </section>
        ) : null}

        <section>
          <SectionTitle eyebrow="Önemli hareketler" title="Gelişen ve gerileyen konular" description="Bu listede yalnızca en az 5 puan yükselen veya gerileyen konular yer alır." />
          {teacherReport.trends.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {teacherReport.trends.map((trend) => <TrendCard key={`${trend.topic}-${trend.from}-${trend.to}`} trend={trend} />)}
            </div>
          ) : <EmptyState title="Belirgin bir değişim yok" description="Bu raporda gösterilecek ölçüde yükselen veya gerileyen bir konu bulunmuyor." />}
        </section>

        <footer className="rounded-2xl border border-slate-200 bg-white px-5 py-4 text-xs leading-5 text-slate-500">Konu seviyeleri sınıfın mevcut deneme sonuçlarını özetler. Öğretim planı oluşturulurken soru içeriği, sınıf içi gözlem ve öğrencilerin bireysel ihtiyaçları da birlikte değerlendirilmelidir.</footer>
      </div>
      </main>
    </>
  );
}
