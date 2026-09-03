"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";

/**
 * 统一状态协议（评审 P1）：loading / error / stale / success + 模块级缓存。
 *
 * - 首次加载：loading=true，渲染骨架（token 页 P0 空白修复）
 * - 有缓存：立即回放旧数据（stale=true）+ 后台刷新，界面永不空白
 * - 失败：error + 如有旧数据继续展示（stale 数据优于空白）
 * - reload()：手动重试（换 nonce 触发）
 */

type CacheEntry = { data: unknown; ts: number };

const CACHE = new Map<string, CacheEntry>();
const TTL = 30_000;

export function useApi<T>(path: string | null, ttlMs = TTL) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(!!path);
  const [stale, setStale] = useState(false);
  const [fetchedAt, setFetchedAt] = useState<number | null>(null);
  const nonceRef = useRef(0);

  const load = useCallback(
    async (silent: boolean) => {
      if (!path) return;
      const nonce = ++nonceRef.current;
      if (!silent) setLoading(true);
      setError(null);
      try {
        const result = await api<T>(path);
        if (nonceRef.current !== nonce) return;
        CACHE.set(path, { data: result, ts: Date.now() });
        setData(result);
        setStale(false);
        setFetchedAt(Date.now());
      } catch (e) {
        if (nonceRef.current !== nonce) return;
        setError(e instanceof ApiError ? e : new ApiError(0, "unknown", String(e)));
        // 失败时保留旧数据展示
      } finally {
        if (nonceRef.current === nonce) setLoading(false);
      }
    },
    [path],
  );

  useEffect(() => {
    if (!path) {
      setData(null);
      setLoading(false);
      return;
    }
    const cached = CACHE.get(path);
    if (cached) {
      setData(cached.data as T);
      setFetchedAt(cached.ts);
      const fresh = Date.now() - cached.ts < ttlMs;
      if (fresh) {
        setStale(false);
        setLoading(false);
        setError(null);
        return;
      }
      setStale(true); // 旧数据先上屏，后台刷新
    }
    load(!cached);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  const reload = useCallback(() => load(false), [load]);

  return { data, error, loading, stale, fetchedAt, reload };
}

export function ageLabel(fetchedAt: number | null): string {
  if (!fetchedAt) return "";
  const sec = Math.floor((Date.now() - fetchedAt) / 1000);
  if (sec < 5) return "刚刚更新";
  if (sec < 60) return `${sec}s 前`;
  return `${Math.floor(sec / 60)}m 前`;
}
