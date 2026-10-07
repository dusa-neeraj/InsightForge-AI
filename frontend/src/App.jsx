import { lazy, Suspense } from "react";
import { Link, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import { EmptyState, Spinner } from "./components/ui.jsx";
import Cleaning from "./pages/Cleaning.jsx";
import ComingSoon from "./pages/ComingSoon.jsx";
import Home from "./pages/Home.jsx";
import Overview from "./pages/Overview.jsx";
import Quality from "./pages/Quality.jsx";
import Upload from "./pages/Upload.jsx";

// Plotly is large, so the dashboard code is only downloaded when the page is opened
const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));

function NotFound() {
  return (
    <EmptyState
      title="Page not found"
      text="That page doesn't exist."
      action={
        <Link to="/" className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700">
          Go home
        </Link>
      }
    />
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="upload" element={<Upload />} />
        <Route path="datasets/:datasetId/overview" element={<Overview />} />
        <Route path="datasets/:datasetId/quality" element={<Quality />} />
        <Route path="datasets/:datasetId/cleaning" element={<Cleaning />} />
        <Route
          path="datasets/:datasetId/dashboard"
          element={
            <Suspense fallback={<Spinner label="Loading charts..." />}>
              <Dashboard />
            </Suspense>
          }
        />
        <Route path="datasets/:datasetId/:page" element={<ComingSoon />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}