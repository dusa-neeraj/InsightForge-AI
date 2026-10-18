import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadDataset } from "../api/client.js";
import Notice from "../components/Notice.jsx";
import { ErrorBanner, PageHeader } from "../components/ui.jsx";
import { formatBytes } from "../lib/format.js";
import { addRecent } from "../lib/recent.js";

const MAX_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB) || 10;
const ALLOWED = [".csv", ".xlsx"];

// Returns { message, tip } when the file can't be used, or null when it is fine
function validate(file) {
  const name = file.name.toLowerCase();
  if (!ALLOWED.some((ext) => name.endsWith(ext))) {
    return { message: "Only .csv and .xlsx files are supported.", tip: "Export or save your data as CSV or Excel." };
  }
  if (file.size === 0) {
    return { message: "That file is empty.", tip: "Check that you picked the right file." };
  }
  if (file.size > MAX_MB * 1024 * 1024) {
    return {
      message: `That file is ${formatBytes(file.size)}, and the limit is ${MAX_MB} MB.`,
      tip: "Try saving it as CSV (smaller than Excel), or upload a sample of the rows.",
    };
  }
  return null;
}

export default function Upload() {
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [problem, setProblem] = useState(null); // the chosen file can't be used
  const [error, setError] = useState(null); // the upload itself failed
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState("idle"); // idle | uploading | analyzing
  const busy = phase !== "idle";

  function choose(selected) {
    if (!selected || busy) return;
    const found = validate(selected);
    setError(null);
    setProblem(found);
    setFile(found ? null : selected);
  }

  async function submit() {
    if (!file || busy) return;
    setError(null);
    setProgress(0);
    setPhase("uploading");
    try {
      const result = await uploadDataset(file, (percent) => {
        setProgress(percent);
        if (percent >= 100) setPhase("analyzing");
      });
      addRecent({
        id: result.dataset_id,
        filename: result.filename,
        rows: result.report.rows_after,
        at: Date.now(),
      });
      navigate(`/datasets/${result.dataset_id}/overview`);
    } catch (err) {
      setError(err.message);
      setPhase("idle");
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Upload a dataset"
        subtitle={`CSV or Excel (.xlsx), up to ${MAX_MB} MB. It's cleaned and analyzed automatically.`}
      />

      <div
        role="button"
        tabIndex={0}
        onClick={() => !busy && inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !busy && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          choose(e.dataTransfer.files[0]);
        }}
        className={`cursor-pointer rounded-2xl border-2 border-dashed bg-white p-10 text-center transition ${
          dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 hover:border-indigo-400"
        } ${busy ? "pointer-events-none opacity-60" : ""}`}
      >
        <p className="text-4xl">📄</p>
        <p className="mt-3 font-medium text-slate-800">Drag a file here, or click to browse</p>
        <p className="mt-1 text-sm text-slate-500">.csv or .xlsx</p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={(e) => {
            choose(e.target.files[0]);
            e.target.value = "";
          }}
        />
      </div>

      {problem && (
        <div className="mt-4">
          <Notice tone="amber" title="This file can't be uploaded">
            <p>{problem.message}</p>
            <p className="mt-1 text-xs">{problem.tip}</p>
          </Notice>
        </div>
      )}

      {error && (
        <div className="mt-4">
          <ErrorBanner message={error} />
        </div>
      )}

      {file && (
        <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-medium text-slate-900">{file.name}</p>
              <p className="text-xs text-slate-500">{formatBytes(file.size)}</p>
            </div>
            {!busy && (
              <button onClick={() => setFile(null)} className="text-sm text-slate-400 hover:text-red-600">
                Remove
              </button>
            )}
          </div>

          {busy ? (
            <div className="mt-4">
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full rounded-full bg-indigo-600 transition-all ${
                    phase === "analyzing" ? "animate-pulse" : ""
                  }`}
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="mt-2 text-sm text-slate-500">
                {phase === "uploading" ? `Uploading... ${progress}%` : "Cleaning and profiling your data..."}
              </p>
            </div>
          ) : (
            <button
              onClick={submit}
              className="mt-4 w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
            >
              Analyze dataset
            </button>
          )}
        </div>
      )}

      <p className="mt-6 text-xs text-slate-400">
        Your file stays on your own server. If AI features are turned on, only summary statistics
        and column names are sent to the AI provider, never individual rows.
      </p>
    </div>
  );
}