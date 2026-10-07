import { useParams } from "react-router-dom";
import { getQuality } from "../api/client.js";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "../components/ui.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { formatNumber, formatPercent } from "../lib/format.js";

const GRADE_TONE = { Excellent: "green", Good: "green", Fair: "amber", Poor: "red" };
const SEVERITY = {
  high: { label: "High", tone: "red" },
  medium: { label: "Medium", tone: "amber" },
  low: { label: "Low", tone: "sky" },
  info: { label: "Info", tone: "slate" },
};
const COMPONENT_LABEL = {
  completeness: "Completeness (no missing values)",
  uniqueness: "Uniqueness (no duplicate rows)",
  outliers: "Outliers (few extreme values)",
};
const COMPARE_ROWS = [
  ["Rows", "rows", (v) => formatNumber(v, 0)],
  ["Duplicate rows", "duplicate_rows", (v) => formatNumber(v, 0)],
  ["Missing cells", "missing_cells", (v) => formatNumber(v, 0)],
  ["Missing %", "missing_pct", formatPercent],
  ["Outlier cells", "outlier_cells", (v) => formatNumber(v, 0)],
];

function barColor(score) {
  if (score >= 75) return "bg-emerald-500";
  return score >= 50 ? "bg-amber-500" : "bg-red-500";
}

function ScoreCard({ title, snapshot, emphasis }) {
  return (
    <div className={`rounded-xl border bg-white p-5 shadow-sm ${emphasis ? "border-indigo-300" : "border-slate-200"}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</p>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-4xl font-bold text-slate-900">{formatNumber(snapshot.score, 1)}</span>
        <span className="text-slate-400">/ 100</span>
        <Badge tone={GRADE_TONE[snapshot.grade]}>{snapshot.grade}</Badge>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${barColor(snapshot.score)}`} style={{ width: `${snapshot.score}%` }} />
      </div>
    </div>
  );
}

export default function Quality() {
  const { datasetId } = useParams();
  const state = useAsync(() => getQuality(datasetId), [datasetId]);

  if (state.loading) return <Spinner label="Checking data quality..." />;
  if (state.error) return <ErrorBanner message={state.error.message} onRetry={state.reload} />;

  const q = state.data.quality;
  const gained = q.score_improvement;
  const counts = Object.entries(q.issue_counts).filter(([, n]) => n > 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Data quality"
        subtitle="How trustworthy the data is, before and after automatic cleaning"
      />

      <div className="grid gap-4 md:grid-cols-3">
        <ScoreCard title="Before cleaning" snapshot={q.before} />
        <ScoreCard title="After cleaning" snapshot={q.after} emphasis />
        <div className="flex flex-col justify-center rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Improvement</p>
          <p className={`mt-2 text-4xl font-bold ${gained > 0 ? "text-emerald-600" : "text-slate-700"}`}>
            {gained > 0 ? "+" : ""}
            {formatNumber(gained, 1)}
          </p>
          <p className="mt-1 text-sm text-slate-500">points from cleaning</p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="How the score is calculated">
          <ul className="space-y-4 p-4">
            {Object.entries(q.after.components).map(([name, value]) => (
              <li key={name}>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-700">{COMPONENT_LABEL[name]}</span>
                  <span className="text-slate-500">
                    {formatNumber(value, 1)} · weight {Math.round(q.score_weights[name] * 100)}%
                  </span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className={`h-full rounded-full ${barColor(value)}`} style={{ width: `${value}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Before vs after">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Measure</th>
                <th className="px-4 py-2 font-medium">Before</th>
                <th className="px-4 py-2 font-medium">After</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {COMPARE_ROWS.map(([label, key, format]) => (
                <tr key={key}>
                  <td className="px-4 py-2 text-slate-600">{label}</td>
                  <td className="px-4 py-2 text-slate-700">{format(q.before[key])}</td>
                  <td className="px-4 py-2 font-medium text-slate-900">{format(q.after[key])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <Card title="Remaining issues">
        {counts.length > 0 && (
          <div className="flex flex-wrap gap-2 border-b border-slate-100 px-4 py-3">
            {counts.map(([level, n]) => (
              <Badge key={level} tone={SEVERITY[level].tone}>
                {n} {SEVERITY[level].label.toLowerCase()}
              </Badge>
            ))}
          </div>
        )}
        {q.issues.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">No issues found. Your data looks clean.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {q.issues.map((issue, i) => (
              <li key={i} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <Badge tone={SEVERITY[issue.severity].tone}>{SEVERITY[issue.severity].label}</Badge>
                <span className="text-slate-700">{issue.message}</span>
                {issue.column && <Badge>{issue.column}</Badge>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}