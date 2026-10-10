import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { deleteDataset } from "../api/client.js";
import { removeRecent } from "../lib/recent.js";

export default function DeleteDatasetButton({ datasetId }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function remove() {
    if (!window.confirm("Delete this dataset and everything generated from it? This cannot be undone.")) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteDataset(datasetId);
    } catch (err) {
      if (err.status !== 404) {
        setError(err.message); // a 404 means it is already gone, which is fine
        setBusy(false);
        return;
      }
    }
    removeRecent(datasetId);
    navigate("/");
  }

  return (
    <>
      <button
        onClick={remove}
        disabled={busy}
        className="rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
      >
        {busy ? "Deleting..." : "Delete dataset"}
      </button>
      {error && (
        <span role="alert" className="self-center text-xs text-red-600">
          {error}
        </span>
      )}
    </>
  );
}