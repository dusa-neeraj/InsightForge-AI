import { useCallback, useEffect, useState } from "react";

// Runs an async function when `deps` change and tracks loading / error / data.
// Each result is stored with the request it belongs to, so "loading" is simply
// "the stored result is for an older request". This also drops stale responses.
export function useAsync(fn, deps) {
  const [tick, setTick] = useState(0);
  const [result, setResult] = useState({ key: null, data: null, error: null });
  const key = JSON.stringify([...deps, tick]);

  useEffect(() => {
    let cancelled = false;
    fn().then(
      (data) => {
        if (!cancelled) setResult({ key, data, error: null });
      },
      (error) => {
        if (!cancelled) setResult({ key, data: null, error });
      }
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const loading = result.key !== key;
  return {
    data: loading ? null : result.data,
    error: loading ? null : result.error,
    loading,
    reload,
  };
}