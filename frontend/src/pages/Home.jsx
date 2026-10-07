import { useState } from "react";
import { Link } from "react-router-dom";
import { Card } from "../components/ui.jsx";
import { formatNumber } from "../lib/format.js";
import { getRecent, removeRecent } from "../lib/recent.js";

const STEPS = [
  { title: "Upload", text: "Drop in a CSV or Excel file." },
  { title: "Clean", text: "Duplicates, missing values and types are fixed automatically." },
  { title: "Explore", text: "KPIs, charts and a data-quality report appear on their own." },
  { title: "Ask", text: "Ask questions in plain English, or write SQL." },
];

export default function Home() {
  const [recent, setRecent] = useState(getRecent);

  return (
    <div className="space-y-8">
      <section className="rounded-2xl bg-gradient-to-br from-indigo-600 to-indigo-800 p-8 text-white shadow-sm sm:p-12">
        <h1 className="text-3xl font-bold sm:text-4xl">Your AI data analyst</h1>
        <p className="mt-3 max-w-2xl text-indigo-100">
          Upload a dataset and get it cleaned, profiled, visualized and explained, then ask it
          questions in plain English.
        </p>
        <Link
          to="/upload"
          className="mt-6 inline-block rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-indigo-700 hover:bg-indigo-50"
        >
          Upload a dataset
        </Link>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((step, index) => (
          <div key={step.title} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-50 text-sm font-bold text-indigo-700">
              {index + 1}
            </span>
            <h2 className="mt-3 font-semibold text-slate-900">{step.title}</h2>
            <p className="mt-1 text-sm text-slate-500">{step.text}</p>
          </div>
        ))}
      </section>

      {recent.length > 0 && (
        <Card title="Recent datasets">
          <ul className="divide-y divide-slate-100">
            {recent.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <Link to={`/datasets/${item.id}/overview`} className="min-w-0 flex-1">
                  <p className="truncate font-medium text-indigo-700 hover:underline">{item.filename}</p>
                  <p className="text-xs text-slate-500">
                    {formatNumber(item.rows, 0)} rows · {new Date(item.at).toLocaleString()}
                  </p>
                </Link>
                <button
                  onClick={() => setRecent(removeRecent(item.id))}
                  className="text-xs text-slate-400 hover:text-red-600"
                >
                  Remove from list
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}