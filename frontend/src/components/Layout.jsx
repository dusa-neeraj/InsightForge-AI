import { useState } from "react";
import { Link, NavLink, Outlet, useLocation, useMatch } from "react-router-dom";
import { getHealth } from "../api/client.js";
import { useAsync } from "../hooks/useAsync.js";
import { DATASET_NAV } from "../lib/nav.js";
import { recentName } from "../lib/recent.js";
import ErrorBoundary from "./ErrorBoundary.jsx";
import { Badge } from "./ui.jsx";

function BackendStatus() {
  const health = useAsync(getHealth, []);
  const color = health.loading ? "bg-slate-300" : health.error ? "bg-red-500" : "bg-emerald-500";
  const text = health.loading ? "Checking server..." : health.error ? "Backend offline" : "Backend online";
  return (
    <div className="flex items-center gap-2 text-xs text-slate-500">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {text}
    </div>
  );
}

export default function Layout() {
  const match = useMatch("/datasets/:datasetId/*");
  const location = useLocation();
  const datasetId = match?.params.datasetId;
  const [open, setOpen] = useState(false);

  const linkClass = ({ isActive }) =>
    `flex items-center justify-between rounded-lg px-3 py-2 text-sm font-medium transition ${
      isActive ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"
    }`;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
        <button
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-slate-600"
        >
          ☰
        </button>
        <span className="font-semibold text-slate-900">AI Data Analyst</span>
      </header>

      {open && (
        <div onClick={() => setOpen(false)} className="fixed inset-0 z-20 bg-slate-900/30 lg:hidden" />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-slate-200 bg-white p-4 transition-transform lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <Link to="/" onClick={() => setOpen(false)} className="mb-6 flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 font-bold text-white">
            A
          </span>
          <span className="font-semibold text-slate-900">AI Data Analyst</span>
        </Link>

        <nav className="space-y-1">
          <NavLink to="/" end className={linkClass} onClick={() => setOpen(false)}>
            Home
          </NavLink>
          <NavLink to="/upload" className={linkClass} onClick={() => setOpen(false)}>
            Upload dataset
          </NavLink>
        </nav>

        {datasetId && (
          <nav className="mt-6 space-y-1">
            <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
              {recentName(datasetId) || "This dataset"}
            </p>
            {DATASET_NAV.map((item) => (
              <NavLink
                key={item.path}
                to={`/datasets/${datasetId}/${item.path}`}
                className={linkClass}
                onClick={() => setOpen(false)}
              >
                {item.label}
                {!item.ready && <Badge>Soon</Badge>}
              </NavLink>
            ))}
          </nav>
        )}

        <div className="mt-auto pt-6">
          <BackendStatus />
        </div>
      </aside>

      <main className="lg:pl-64">
        <div className="mx-auto max-w-6xl p-4 sm:p-8">
          {/* the key resets the boundary when you move to another page */}
          <ErrorBoundary key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}