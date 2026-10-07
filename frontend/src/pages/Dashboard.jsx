import { useState } from "react";
import { useParams } from "react-router-dom";
import { getCharts, getKpis } from "../api/client.js";
import PlotlyChart from "../components/PlotlyChart.jsx";
import { Card, EmptyState, ErrorBanner, PageHeader, Spinner } from "../components/ui.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { kpiValue } from "../lib/format.js";
import { CURRENCIES, getCurrency, setCurrency } from "../lib/settings.js";

const SECTIONS = [
  ["trends", "Trends over time"],
  ["comparisons", "Comparisons"],
  ["categories", "Categories"],
  ["distributions", "Distributions"],
  ["relationships", "Relationships"],
];
const WIDE_CHARTS = new Set(["line", "heatmap"]);
const DIRECTION = {
  up: { arrow: "▲", color: "text-emerald-600" },
  down: { arrow: "▼", color: "text-red-600" },
  flat: { arrow: "■", color: "text-slate-500" },
};

function KpiCard({ card, currency }) {
  const direction = card.direction ? DIRECTION[card.direction] : null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{card.label}</p>
      <p className={`mt-1 truncate text-2xl font-bold ${direction ? direction.color : "text-slate-900"}`}>
        {direction && <span className="mr-1 text-base">{direction.arrow}</span>}
        {kpiValue(card, currency)}
      </p>
      {card.subtitle && <p className="mt-1 text-xs text-slate-500">{card.subtitle}</p>}
    </div>
  );
}

function rolesLine(roles) {
  const parts = [];
  if (roles.primary_measure) parts.push(`main measure: ${roles.primary_measure}`);
  if (roles.dimensions.length) parts.push(`grouped by: ${roles.dimensions.join(", ")}`);
  if (roles.date_column) parts.push(`dates: ${roles.date_column}`);
  return parts.length ? `KPIs are based on ${parts.join(" · ")}` : null;
}

function KpiSection({ state, currency }) {
  if (state.loading) return <Spinner label="Calculating KPIs..." />;
  if (state.error) return <ErrorBanner message={state.error.message} onRetry={state.reload} />;
  const { cards, roles } = state.data.kpis;
  const note = rolesLine(roles);
  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <KpiCard key={card.id} card={card} currency={currency} />
        ))}
      </div>
      {note && <p className="mt-3 text-xs text-slate-400">{note}</p>}
    </div>
  );
}

function ChartSection({ state }) {
  if (state.loading) return <Spinner label="Drawing charts..." />;
  if (state.error) return <ErrorBanner message={state.error.message} onRetry={state.reload} />;
  const { charts, skipped } = state.data;
  if (charts.length === 0) {
    return (
      <EmptyState
        title="No charts for this dataset"
        text="There wasn't enough numeric, category or date data to draw useful charts."
      />
    );
  }
  return (
    <div className="space-y-8">
      {SECTIONS.map(([key, title]) => {
        const items = charts.filter((chart) => chart.section === key);
        if (items.length === 0) return null;
        return (
          <section key={key}>
            <h2 className="mb-3 text-lg font-semibold text-slate-900">{title}</h2>
            <div className="grid gap-4 md:grid-cols-2">
              {items.map((chart) => (
                <div
                  key={chart.id}
                  className={WIDE_CHARTS.has(chart.type) ? "md:col-span-2" : ""}
                >
                  <Card title={chart.title}>
                    <div className="p-3">
                      <PlotlyChart figure={chart.figure} label={chart.title} />
                    </div>
                    <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
                      Why this chart: {chart.reason}
                    </p>
                  </Card>
                </div>
              ))}
            </div>
          </section>
        );
      })}
      {skipped.length > 0 && (
        <p className="text-xs text-slate-400">
          {skipped.length} chart{skipped.length === 1 ? "" : "s"} could not be generated.
        </p>
      )}
    </div>
  );
}

export default function Dashboard() {
  const { datasetId } = useParams();
  const kpis = useAsync(() => getKpis(datasetId), [datasetId]);
  const charts = useAsync(() => getCharts(datasetId), [datasetId]);
  const [currency, setCurrencyState] = useState(getCurrency);

  function changeCurrency(symbol) {
    setCurrencyState(symbol);
    setCurrency(symbol);
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Dashboard"
        subtitle="Key numbers and charts, chosen automatically from your data"
        actions={
          <label className="flex items-center gap-2 text-sm text-slate-600">
            Currency
            <select
              value={currency}
              onChange={(e) => changeCurrency(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm"
            >
              {CURRENCIES.map((option) => (
                <option key={option.symbol} value={option.symbol}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        }
      />
      <KpiSection state={kpis} currency={currency} />
      <ChartSection state={charts} />
    </div>
  );
}