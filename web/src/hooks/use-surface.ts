import { useCallback, useEffect, useRef, useState } from "react";

export type SurfaceState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  reloading: boolean;
  reload: () => void;
};

export function useSurface<T>(load: () => Promise<T>): SurfaceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloading, setReloading] = useState(false);
  const loadRef = useRef(load);

  useEffect(() => {
    loadRef.current = load;
  });

  const run = useCallback(async (asReload: boolean) => {
    setError(null);
    if (asReload) setReloading(true);
    else setLoading(true);
    try {
      const result = await loadRef.current();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setLoading(false);
      setReloading(false);
    }
  }, []);

  useEffect(() => {
    // Allowed: firing the initial fetch from mount, matching the codebase pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void run(false);
  }, [run]);

  const reload = useCallback(() => void run(true), [run]);

  return { data, error, loading, reloading, reload };
}