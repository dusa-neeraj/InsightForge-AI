import { useParams } from "react-router-dom";
import { getQuality } from "../api/client.js";
import { Badge, Card, ErrorBanner, PageHeader, Spinner, StatCard } from "../components/ui.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { formatNumber } from "../lib/format.js";

const ICONS = {
  columns_renamed: "✏️",
  empty_rows_removed: "🧹",
  empty_column_dropped: "🗑️",
  placeholders_to_missing: "🔎",
  type_converted: "🔢",
  values_standardized: "🔤",
  duplicates_removed: "♻️",
  missing_filled: "🩹",
  missing_left: "⚠️",
  outliers_flagged: "🚩",
  no_changes: "✅",
};

export default function Cleaning() {
  const { datasetId } = useParams();
  const state = useAsync(() => getQuality(datasetId), [datasetId]);

  if (state.loading) return <Spinner label="Loading cleaning report..." />;
  if (state.error) return <ErrorBanner message={state.error.message} onRetry={state.reload} />;

  const { before, after, changes } = state.data.quality;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Cleaning report"
        subtitle="Every change made to your data, in the order it happened"
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Rows" value={`${formatNumber(before.rows, 0)} → ${formatNumber(after.rows, 0)}`} />
        <StatCard label="Columns" value={`${formatNumber(before.columns, 0)} → ${formatNumber(after.columns, 0)}`} />
        <StatCard label="Quality score" value={`${formatNumber(before.score, 1)} → ${formatNumber(after.score, 1)}`} />
      </div>

      <Card title={`${changes.length} step${changes.length === 1 ? "" : "s"}`}>
        <ol className="divide-y divide-slate-100">
          {changes.map((change, i) => (
            <li key={i} className="flex items-start gap-3 px-4 py-3">
              <span className="mt-0.5 w-6 text-center text-lg" aria-hidden="true">
                {ICONS[change.type] || "•"}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-slate-800">{change.message}</p>
                <div className="mt-1 flex flex-wrap gap-2">
                  {change.column && <Badge tone="indigo">{change.column}</Badge>}
                  {change.count != null && <Badge>{formatNumber(change.count, 0)} affected</Badge>}
                </div>
              </div>
              <span className="text-xs text-slate-400">Step {i + 1}</span>
            </li>
          ))}
        </ol>
      </Card>

      <p className="text-sm text-slate-500">
        Outliers are flagged but never deleted, so you always decide whether an extreme value is an
        error or a real case.
      </p>
    </div>
  );
}