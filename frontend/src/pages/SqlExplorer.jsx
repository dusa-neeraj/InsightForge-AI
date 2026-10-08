import { useState } from "react";
import { useParams } from "react-router-dom";
import { getSqlSchema, runSql } from "../api/client.js";
import DataTable from "../components/DataTable.jsx";
import Notice from "../components/Notice.jsx";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { formatNumber } from "../lib/format.js";

const STATUS = {
  rejected: { tone: "red", title: "Blocked for safety" },
  error: { tone: "amber", title: "The query failed" },
  unsupported: { tone: "slate", title: "Can't answer that with SQL" },
};
const SOURCE = { user: "Your SQL", ai: "Written by AI", rules: "Built from keywords" };
const TYPE_TONE = { INTEGER: "indigo", REAL: "indigo", TEXT: "sky" };

function SqlBlock({ sql, source, explanation }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard access is not available
    }
  }

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-700">SQL that ran</span>
          <Badge tone={source === "user" ? "slate" : "indigo"}>{SOURCE[source]}</Badge>
        </div>
        <button onClick={copy} className="text-xs font-medium text-indigo-600 hover:underline">
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto bg-slate-900 p-4 text-sm leading-6 text-slate-100">
        <code>{sql}</code>
      </pre>
      {explanation && <p className="px-4 py-2 text-xs text-slate-500">{explanation}</p>}
    </section>
  );
}

function Outcome({ outcome }) {
  if (outcome.error) {
    return (
      <Notice tone="red" title="Request failed">
        {outcome.error}
      </Notice>
    );
  }
  const r = outcome.response;
  const status = STATUS[r.status];
  return (
    <div className="space-y-4">
      {status && (
        <Notice tone={status.tone} title={status.title}>
          {r.message}
        </Notice>
      )}
      {r.note && <p className="text-xs text-slate-500">{r.note}</p>}
      {r.sql && <SqlBlock sql={r.sql} source={r.source} explanation={r.explanation} />}
      {r.status === "ok" && (
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-2 text-sm">
            <span className="font-semibold text-slate-700">Result</span>
            <span className="text-xs text-slate-500">
              {formatNumber(r.row_count, 0)} row(s) · {r.elapsed_ms} ms
              {r.truncated ? " · limited to the first 1,000 rows" : ""}
            </span>
          </div>
          {r.rows.length > 0 ? (
            <DataTable columns={r.columns} rows={r.rows} maxRows={200} height="max-h-96" />
          ) : (
            <p className="p-4 text-sm text-slate-500">The query ran but returned no rows.</p>
          )}
        </section>
      )}
    </div>
  );
}

function SchemaPanel({ state, onPick }) {
  if (state.loading) return <Spinner label="Loading schema..." />;
  if (state.error) return <ErrorBanner message={state.error.message} onRetry={state.reload} />;
  const { table, rows, columns, notes } = state.data;
  return (
    <Card title={`Table: ${table} (${formatNumber(rows, 0)} rows)`}>
      <ul className="max-h-72 divide-y divide-slate-100 overflow-auto">
        {columns.map((col) => (
          <li key={col.name}>
            <button
              onClick={() => onPick(col.name)}
              title="Click to add to the editor"
              className="flex w-full items-center justify-between px-4 py-2 text-left text-sm hover:bg-slate-50"
            >
              <span className="font-mono text-slate-800">{col.name}</span>
              <Badge tone={TYPE_TONE[col.type] || "slate"}>{col.type}</Badge>
            </button>
          </li>
        ))}
      </ul>
      <ul className="space-y-1 border-t border-slate-100 p-4 text-xs text-slate-500">
        {notes.map((note, i) => (
          <li key={i}>• {note}</li>
        ))}
      </ul>
    </Card>
  );
}

function SqlWorkspace({ datasetId }) {
  const schema = useAsync(() => getSqlSchema(datasetId), [datasetId]);
  const [question, setQuestion] = useState("");
  const [sql, setSql] = useState("SELECT * FROM data LIMIT 10");
  const [running, setRunning] = useState(null); // "question" | "sql" | null
  const [outcome, setOutcome] = useState(null);
  const busy = running !== null;

  async function run(body, mode) {
    if (busy) return;
    setRunning(mode);
    setOutcome(null);
    try {
      const response = await runSql(datasetId, body);
      setOutcome({ response });
      if (mode === "question" && response.sql) setSql(response.sql); // lets you edit what was generated
    } catch (err) {
      setOutcome({ error: err.message });
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="SQL explorer"
        subtitle="Ask in plain English or write your own SELECT. Queries run on a safe, read-only copy."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          <Card title="Ask in plain English">
            <div className="flex flex-col gap-2 p-4 sm:flex-row">
              <input
                value={question}
                maxLength={500}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && question.trim() && run({ question }, "question")}
                placeholder='e.g. "Which product has the highest revenue?"'
                className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <button
                onClick={() => run({ question }, "question")}
                disabled={busy || !question.trim()}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {running === "question" ? "Working..." : "Generate & run"}
              </button>
            </div>
          </Card>

          <Card title="SQL editor">
            <div className="p-4">
              <textarea
                value={sql}
                maxLength={2000}
                spellCheck={false}
                rows={6}
                onChange={(e) => setSql(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") run({ sql }, "sql");
                }}
                className="w-full rounded-lg border border-slate-300 bg-slate-900 p-3 font-mono text-sm text-slate-100"
              />
              <div className="mt-3 flex items-center justify-between gap-3">
                <p className="text-xs text-slate-400">Ctrl + Enter to run · SELECT only</p>
                <button
                  onClick={() => run({ sql }, "sql")}
                  disabled={busy || !sql.trim()}
                  className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {running === "sql" ? "Running..." : "Run SQL"}
                </button>
              </div>
            </div>
          </Card>

          {busy && <Spinner label="Running query..." />}
          {outcome && !busy && <Outcome outcome={outcome} />}
        </div>

        <aside>
          <SchemaPanel state={schema} onPick={(name) => setSql((current) => `${current} ${name}`)} />
        </aside>
      </div>
    </div>
  );
}

// The key resets the editor and results when you switch datasets
export default function SqlExplorer() {
  const { datasetId } = useParams();
  return <SqlWorkspace key={datasetId} datasetId={datasetId} />;
}