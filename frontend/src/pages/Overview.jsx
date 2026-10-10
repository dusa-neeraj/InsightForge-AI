import { Link, useParams } from "react-router-dom";
import { getPreview, getProfile } from "../api/client.js";
import { Badge, Card, ErrorBanner, PageHeader, Spinner, StatCard } from "../components/ui.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { formatNumber, formatPercent } from "../lib/format.js";
import { recentName } from "../lib/recent.js";
import DeleteDatasetButton from "../components/DeleteDatasetButton.jsx";

const KIND = {
  numeric: { label: "Number", tone: "indigo" },
  categorical: { label: "Text", tone: "sky" },
  date: { label: "Date", tone: "amber" },
};

function summarize(col) {
  if (col.kind === "numeric" && col.min != null) {
    return `${formatNumber(col.min)} to ${formatNumber(col.max)} · avg ${formatNumber(col.mean)}`;
  }
  if (col.kind === "date" && col.min) return `${col.min.slice(0, 10)} to ${col.max.slice(0, 10)}`;
  const top = col.top_values?.[0];
  return top ? `Most common: ${top.value} (${formatPercent(top.pct)})` : "—";
}

function missingTone(pct) {
  if (pct === 0) return "text-slate-500";
  return pct > 20 ? "font-medium text-red-600" : "font-medium text-amber-600";
}

function PreviewTable({ preview }) {
  if (preview.loading) return <Spinner label="Loading preview..." />;
  if (preview.error) {
    return (
      <div className="p-4">
        <ErrorBanner message={preview.error.message} onRetry={preview.reload} />
      </div>
    );
  }
  const { columns, rows, total_rows: total } = preview.data;
  return (
    <>
      <div className="max-h-96 overflow-auto">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              {columns.map((name) => (
                <th key={name} className="whitespace-nowrap px-3 py-2 font-medium">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className="whitespace-nowrap px-3 py-2 text-slate-700">
                    {cell === null ? <span className="text-slate-300">—</span> : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
        Showing {rows.length} of {formatNumber(total, 0)} rows (after cleaning)
      </p>
    </>
  );
}

export default function Overview() {
  const { datasetId } = useParams();
  const profile = useAsync(() => getProfile(datasetId), [datasetId]);
  const preview = useAsync(() => getPreview(datasetId, 15), [datasetId]);

  if (profile.loading) return <Spinner label="Loading dataset overview..." />;
  if (profile.error) {
    return (
      <ErrorBanner message={profile.error.message} onRetry={profile.reload}>
        <Link to="/upload" className="text-red-700 underline">
          Upload a dataset
        </Link>
      </ErrorBanner>
    );
  }

  const { overview, columns, column_types: types } = profile.data.profile;

  return (
    <div className="space-y-6">
      <PageHeader
        title={recentName(datasetId) || "Dataset overview"}
        subtitle="What your data looks like after automatic cleaning"
        actions={
          <>
            <DeleteDatasetButton datasetId={datasetId} />
            <Link
              to="/upload"
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Upload another
            </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Rows" value={formatNumber(overview.rows, 0)} hint={`${formatNumber(overview.complete_rows, 0)} complete`} />
        <StatCard
          label="Columns"
          value={formatNumber(overview.columns, 0)}
          hint={`${types.numeric.length} number · ${types.categorical.length} text · ${types.date.length} date`}
        />
        <StatCard
          label="Missing cells"
          value={formatPercent(overview.missing_pct)}
          hint={`${formatNumber(overview.missing_cells, 0)} cells`}
        />
        <StatCard label="Duplicate rows" value={formatNumber(overview.duplicate_rows, 0)} hint="after cleaning" />
      </div>

      <Card title="Columns">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Column</th>
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Missing</th>
                <th className="px-4 py-2 font-medium">Unique</th>
                <th className="px-4 py-2 font-medium">Summary</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {columns.map((col) => (
                <tr key={col.name}>
                  <td className="whitespace-nowrap px-4 py-2 font-medium text-slate-900">
                    {col.name} {col.likely_id && <Badge>ID</Badge>}
                  </td>
                  <td className="px-4 py-2">
                    <Badge tone={KIND[col.kind].tone}>{KIND[col.kind].label}</Badge>
                  </td>
                  <td className={`px-4 py-2 ${missingTone(col.missing_pct)}`}>{formatPercent(col.missing_pct)}</td>
                  <td className="px-4 py-2 text-slate-600">{formatNumber(col.unique, 0)}</td>
                  <td className="px-4 py-2 text-slate-600">{summarize(col)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Data preview">
        <PreviewTable preview={preview} />
      </Card>
    </div>
  );
}