"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type AnalyticsSummary, fetchAnalyticsSummary } from "@/lib/api";

export default function AnalyticsPage() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchAnalyticsSummary(dateFrom || undefined, dateTo || undefined)
      .then((res) => {
        if (mountedRef.current) setSummary(res);
      })
      .catch((err: unknown) => {
        if (mountedRef.current) {
          setError(err instanceof ApiError ? err.message : "KPIの取得に失敗しました");
        }
      })
      .finally(() => {
        if (mountedRef.current) setLoading(false);
      });
  }, [dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-bold">実績分析</h1>

      <div className="mb-4 flex items-center gap-3 text-sm">
        <label className="flex items-center gap-2">
          期間(開始)
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
            className="rounded border border-gray-300 px-2 py-1"
          />
        </label>
        <label className="flex items-center gap-2">
          期間(終了)
          <input
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
            className="rounded border border-gray-300 px-2 py-1"
          />
        </label>
      </div>

      {loading && <p className="text-sm text-gray-500">読み込み中...</p>}
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {summary && !loading && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <p className="text-xs text-gray-500">クリック数</p>
              <p className="text-lg font-semibold text-gray-800">{summary.clicks}</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <p className="text-xs text-gray-500">成果件数</p>
              <p className="text-lg font-semibold text-gray-800">{summary.conversions}</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <p className="text-xs text-gray-500">報酬額</p>
              <p className="text-lg font-semibold text-gray-800">
                {summary.revenue.toLocaleString()}円
              </p>
            </div>
          </div>

          {summary.by_genre.length === 0 ? (
            <p className="text-sm text-gray-500">実績データがありません</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="w-full min-w-[480px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-gray-500">
                    <th className="px-4 py-2 font-medium">ジャンル</th>
                    <th className="px-4 py-2 font-medium">クリック数</th>
                    <th className="px-4 py-2 font-medium">成果件数</th>
                    <th className="px-4 py-2 font-medium">報酬額</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.by_genre.map((genre) => (
                    <tr key={genre.genre_id} className="border-b border-gray-100 last:border-0">
                      <td className="px-4 py-2">{genre.genre_name}</td>
                      <td className="px-4 py-2">{genre.clicks}</td>
                      <td className="px-4 py-2">{genre.conversions}</td>
                      <td className="px-4 py-2">{genre.revenue.toLocaleString()}円</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
