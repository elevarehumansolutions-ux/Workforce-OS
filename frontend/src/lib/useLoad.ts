import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";

interface LoadResult<T> {
  key: string;
  data: T | null;
  error: string;
  status: number | null;
}

export interface LoadState<T> {
  data: T | null;
  error: string;
  // The HTTP status of a failed load (for example 404), otherwise null.
  status: number | null;
  loading: boolean;
}

// Loads something when `key` changes. Change the key (for example by adding a
// reload counter to it) to load again. State is only set from the promise
// callbacks, and "loading" is worked out by comparing keys.
export function useLoad<T>(key: string, loader: () => Promise<T>, fallbackError: string): LoadState<T> {
  const [result, setResult] = useState<LoadResult<T> | null>(null);
  const loaderRef = useRef(loader);
  const fallbackRef = useRef(fallbackError);

  useEffect(function () {
    loaderRef.current = loader;
    fallbackRef.current = fallbackError;
  });

  useEffect(
    function () {
      let cancelled = false;
      loaderRef
        .current()
        .then(function (data) {
          if (cancelled) return;
          setResult({ key: key, data: data, error: "", status: null });
        })
        .catch(function (err) {
          if (cancelled) return;
          setResult({
            key: key,
            data: null,
            error: err instanceof ApiError ? err.message : fallbackRef.current,
            status: err instanceof ApiError ? err.status : null,
          });
        });
      return function () {
        cancelled = true;
      };
    },
    [key]
  );

  const current = result !== null && result.key === key ? result : null;
  return {
    data: current ? current.data : null,
    error: current ? current.error : "",
    status: current ? current.status : null,
    loading: current === null,
  };
}
