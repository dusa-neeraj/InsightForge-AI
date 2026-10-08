import { Fragment, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getInsights } from "../api/client.js";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { formatNumber } from "../lib/format.js";

const IMPORTANCE = {
  high: { label: "High", tone: "red" },
  medium: { label: "Medium", tone: "amber" },
  low: { label: "Low", tone: "slate" },
};
const TYPE_LABEL = {
  composition: "Breakdown",
  trend: "Trend",
  correlation: "Relationship",
  category_effect: "Category effect",
  outliers: "Outliers",
  distribution: "Distribution",
  dominant_category: "Dominant category",
  quality: "Data quality",
  caution: "Caution",
};
const FILTERS = [
  ["all", "All"],
  ["high", "High"],
  ["medium", "Medium"],
  ["low", "Low"],
];

// Turns "[I2]" citations in the AI summary into small badges
function Cited({ text }) {
  return text.split(/(\[I\d+\])/g).map((part, i) =>
    /^\[I\d+\]$/.test(part) ? (
      <span key={i} className="mx-0.5 rounded bg-indigo-50 px-1 text-xs font-medium text-indigo-700">
        {part.slice(1, -1)}
      </span>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

function evidenceValue(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return formatNumber(value, 4);
  return String(value);
}

function InsightItem({ insight }) {
  const importance = IMPORTANCE[insight.importance];
  const evidence = Object.entries(insight.evidence);
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="indigo">{insight.id}</Badge>
        <Badge tone={importance.tone}>{importance.label}</Badge>
        <span className="text-xs text-slate-500">{TYPE_LABEL[insight.type] || insight.type}</span>
      </div>
      <p className="mt-2 text-sm text-slate-800">{insight.message}</p>
      {insight.columns.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {insight.columns.map((column) => (
            <Badge key={column}>{column}</Badge>
          ))}
        </div>
      )}
      {evidence.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-medium text-indigo-600">Show evidence</summary>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg bg-slate-50 p-3 text-xs">
            {evidence.map(([key, value]) => (
              <Fragment key={key}>
                <dt className="text-slate-500">{key.replace(/_/g, " ")}</dt>
                <dd className="font-medium text-slate-800">{evidenceValue(value)}</dd>
              </Fragment>
            ))}
          </dl>
        </details>
      )}
    </li>
  );
}

export default function Insights() {
  const { datasetId } = useParams();
  const navigate = useNavigate();
  const [forced, setForced] = useState(0); // 0 = normal load, 1+ = regenerate
  const [filter, setFilter] = useState("all");
  const state = useAsync(() => getInsights(datasetId, forced > 0), [datasetId, forced]);

  if (state.loading) {
    return <Spinner label="Analyzing your data... (this can take a few seconds when AI is on)" />;
  }
  if (state.error) return <ErrorBanner message={state.error.message} onRetry={state.reload} />;

  const { insights, narration, cached } = state.data;
  const visible = filter === "all" ? insights : insights.filter((item) => item.importance === filter);
  const ask = (question) => navigate(`/datasets/${datasetId}/chat`, { state: { question } });

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI insights"
        subtitle="Findings calculated from your data, with a plain-language summary"
        actions={
          <button
            onClick={() => setForced((n) => n + 1)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Regenerate
          </button>
        }
      />

      <Card>
        <div className="p-5">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-700">Summary</h2>
            {narration.source === "ai" ? (
              <Badge tone="indigo">AI-written · {narration.model}</Badge>
            ) : (
              <Badge>Rule-based</Badge>
            )}
            {cached && <Badge tone="green">Cached</Badge>}
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-800">
            <Cited text={narration.summary} />
          </p>
          {narration.note && <p className="mt-3 text-xs text-slate-500">{narration.note}</p>}
          <p className="mt-3 text-xs text-slate-400">
            Every number in an AI summary is checked against the calculated insights below. If it
            can't be verified, the rule-based summary is shown instead.
          </p>
        </div>
      </Card>

      {(narration.recommendations.length > 0 || narration.questions.length > 0) && (
        <div className="grid gap-6 lg:grid-cols-2">
          {narration.recommendations.length > 0 && (
            <Card title="Suggested next steps">
              <ul className="space-y-2 p-4 text-sm text-slate-700">
                {narration.recommendations.map((text, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-indigo-500">→</span>
                    {text}
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {narration.questions.length > 0 && (
            <Card title="Questions to explore">
              <ul className="space-y-2 p-4">
                {narration.questions.map((text, i) => (
                  <li key={i}>
                    <button
                      onClick={() => ask(text)}
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-left text-sm text-slate-700 hover:border-indigo-300 hover:bg-indigo-50"
                    >
                      {text}
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}

      <Card title={`Insights (${visible.length})`}>
        <div className="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-3">
          {FILTERS.map(([value, label]) => (
            <button
              key={value}
              onClick={() => setFilter(value)}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                filter === value ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {visible.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">No insights at this level.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {visible.map((insight) => (
              <InsightItem key={insight.id} insight={insight} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}