import { Link, useParams } from "react-router-dom";
import { EmptyState } from "../components/ui.jsx";
import { DATASET_NAV } from "../lib/nav.js";

export default function ComingSoon() {
  const { datasetId, page } = useParams();
  const item = DATASET_NAV.find((entry) => entry.path === page);

  if (!item) {
    return <EmptyState title="Page not found" text="That page doesn't exist." />;
  }
  return (
    <EmptyState
      title={`${item.label} is coming soon`}
      text="The backend for this page is already built. The page itself arrives in the next frontend steps."
      action={
        <Link
          to={`/datasets/${datasetId}/overview`}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Back to overview
        </Link>
      }
    />
  );
}