"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  type AnalyticsSummary,
  type CostSummary,
  fetchAnalyticsSummary,
  fetchCandidates,
  fetchContents,
  fetchCosts,
} from "@/lib/api";
import { currentMonthIso, todayIso } from "@/lib/date";

interface DashboardState {
  candidateCount: number;
  needsReviewCount: number;
  cost: CostSummary;
  kpi: AnalyticsSummary;
}

export default function DashboardPage() {
  const [state, setState] = useState<DashboardState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const today = todayIso();
    const month = currentMonthIso();

    setLoading(true);
    setError(null);
    Promise.all([
      fetchCandidates(today),
      fetchContents(["needs_review"]),
      fetchCosts(month),
      fetchAnalyticsSummary(`${month}-01`, today),
    ])
      .then(([candidates, needsReview, cost, kpi]) => {
        if (!mountedRef.current) return;
        setState({
          candidateCount: candidates.meta.total,
          needsReviewCount: needsReview.meta.total,
          cost,
          kpi,
        });
      })
      .catch((err: unknown) => {
        if (mountedRef.current) {
          setError(err instanceof ApiError ? err.message : "ダッシュボードの取得に失敗しました");
        }
      })
      .finally(() => {
        if (mountedRef.current) setLoading(false);
      });
  }, []);

  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-bold">ダッシュボード</h1>

      {loading && <p className="text-sm text-gray-500">読み込み中...</p>}
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {state && !loading && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <p className="text-xs text-gray-500">本日の候補数</p>
              <p className="text-lg font-semibold text-gray-800">{state.candidateCount}</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <p className="text-xs text-gray-500">要確認数</p>
              <p className="text-lg font-semibold text-amber-600">{state.needsReviewCount}</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <p className="text-xs text-gray-500">月間LLMコスト</p>
              <p className="text-lg font-semibold text-gray-800">
                {Math.round(state.cost.total_cost_jpy).toLocaleString()}円
                <span className="ml-1 text-xs font-normal text-gray-400">
                  / {state.cost.budget_jpy.toLocaleString()}円
                </span>
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <p className="text-xs text-gray-500">今月の報酬額</p>
              <p className="text-lg font-semibold text-gray-800">
                {state.kpi.revenue.toLocaleString()}円
              </p>
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold text-gray-700">今月のKPI</h2>
            <div className="flex gap-6 text-sm text-gray-600">
              <span>クリック数: {state.kpi.clicks}</span>
              <span>成果件数: {state.kpi.conversions}</span>
              <span>報酬額: {state.kpi.revenue.toLocaleString()}円</span>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
