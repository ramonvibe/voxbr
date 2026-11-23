"use client";
import { useCallback, useEffect, useState } from "react";
import { api, errMsg } from "./api";

/** GET com loading/erro; `pollMs` repete a busca em segundo plano (pode ser função do dado atual). */
export function useApi<T>(path: string | null, pollMs?: number | ((d: T | undefined) => number | null)) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      setData(await api<T>(path));
      setError(undefined);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    if (!path) return;
    let alive = true;
    api<T>(path)
      .then((d) => alive && (setData(d), setError(undefined)))
      .catch((e) => alive && setError(errMsg(e)))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [path]);

  const ms = typeof pollMs === "function" ? pollMs(data) : pollMs;
  useEffect(() => {
    if (!ms) return;
    const t = setInterval(reload, ms);
    return () => clearInterval(t);
  }, [ms, reload]);

  return { data, error, loading, reload };
}
