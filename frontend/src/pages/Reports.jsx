import { useState } from "react";
import { useParams } from "react-router-dom";
import { downloadFile, openPreview } from "../api/client.js";
import Notice from "../components/Notice.jsx";
import { Card, PageHeader } from "../components/ui.jsx";
import { getCurrency } from "../lib/settings.js";
import { recentName } from "../lib/recent.js";

const CONTENTS = [
  "Dataset summary and quality score",
  "Key findings and suggested next steps",
  "KPIs",
  "Data-quality report (before and after)",
  "Every cleaning step",
  "Statistics for number and text columns",
  "Charts, each with the reason it was chosen",
  "All insights",
];

function DownloadCard({ icon, title, text, action, busy, disabled, onClick }) {
  return (
    <div className="flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-3xl" aria-hidden="true">
        {icon}
      </p>
      <h2 className="mt-3 font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 flex-1 text-sm text-slate-500">{text}</p>
      <button
        onClick={onClick}
        disabled={disabled}
        className="mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? "Working..." : action}
      </button>
    </div>
  );
}

export default function Reports() {
  const { datasetId } = useParams();
  const [busy, setBusy] = useState(null);
  const [notice, setNotice] = useState(null);

  const currency = getCurrency();
  const filename = recentName(datasetId) || "Dataset";
  const base = filename.replace(/\.[^.]+$/, "").replace(/[^\w.-]+/g, "_") || "dataset";
  const query = new URLSearchParams({ name: filename, currency }).toString();
  const root = `/datasets/${datasetId}`;

  async function run(key, task, doneText) {
    if (busy) return;
    setBusy(key);
    setNotice(null);
    try {
      await task();
      setNotice({ tone: "indigo", text: doneText });
    } catch (err) {
      setNotice({ tone: "red", text: err.message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports and downloads"
        subtitle="Take your results with you. Everything is built from the same verified numbers as the dashboard."
      />

      {notice && (
        <Notice tone={notice.tone} title={notice.tone === "red" ? "Could not complete that" : undefined}>
          {notice.text}
        </Notice>
      )}
      {busy && busy !== "csv" && (
        <p className="text-sm text-slate-500">Building the report. This can take a few seconds...</p>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <DownloadCard
          icon="📕"
          title="Analysis report (PDF)"
          text="A shareable, print-ready report with charts."
          action="Download PDF"
          busy={busy === "pdf"}
          disabled={busy !== null}
          onClick={() =>
            run("pdf", () => downloadFile(`${root}/reports/pdf?${query}`, `${base}-report.pdf`), "PDF report downloaded.")
          }
        />
        <DownloadCard
          icon="🌐"
          title="Analysis report (HTML)"
          text="The same report as a single web page. Preview it, or save the file."
          action="Preview in a new tab"
          busy={busy === "preview"}
          disabled={busy !== null}
          onClick={() => run("preview", () => openPreview(`${root}/reports/html?${query}`), "Report opened in a new tab.")}
        />
        <DownloadCard
          icon="🧼"
          title="Cleaned dataset (CSV)"
          text="Your data after automatic cleaning. Opens correctly in Excel."
          action="Download CSV"
          busy={busy === "csv"}
          disabled={busy !== null}
          onClick={() =>
            run("csv", () => downloadFile(`${root}/download/clean.csv`, `${base}-cleaned.csv`), "Cleaned CSV downloaded.")
          }
        />
      </div>

      <button
        onClick={() =>
          run("html", () => downloadFile(`${root}/reports/html?${query}&download=true`, `${base}-report.html`), "HTML report downloaded.")
        }
        disabled={busy !== null}
        className="text-sm font-medium text-indigo-600 hover:underline disabled:opacity-50"
      >
        {busy === "html" ? "Working..." : "Download the HTML report as a file"}
      </button>

      <Card title="What is in the report">
        <ul className="grid gap-2 p-4 text-sm text-slate-700 sm:grid-cols-2">
          {CONTENTS.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="text-indigo-500">✓</span>
              {item}
            </li>
          ))}
        </ul>
        <div className="space-y-1 border-t border-slate-100 p-4 text-xs text-slate-500">
          <p>Money values use the currency chosen on the Dashboard: {currency || "no symbol"}.</p>
          <p>
            The PDF uses a standard font, so characters outside Western European text (and the ₹ sign,
            written as "Rs") may not display. The HTML report shows everything.
          </p>
          <p>AI-written text is included only if you already generated it on the AI Insights page.</p>
        </div>
      </Card>
    </div>
  );
}