"use client";

import { useEffect, useState } from "react";
import { ApiError, type Candidate, fetchCandidates } from "@/lib/api";
import { todayIso } from "@/lib/date";

const SCORE_LABELS: Record<string, string> = {
  rank_trend: "順位変動",
  review_growth: "レビュー増加率",
  rating: "評価",
  seasonality: "季節性",
  price_fit: "価格帯適合",
  competition: "競合度",
};

function ScoreCell({ candidate }: { candidate: Candidate }) {
  return (
    <div className="group relative inline-block cursor-default font-mono">
      {candidate.score.toFixed(3)}
      <div className="pointer-events-none absolute left-1/2 top-full z-10 mt-1 hidden w-56 -translate-x-1/2 rounded-md border border-gray-200 bg-white p-3 text-xs normal-case text-gray-700 shadow-lg group-hover:block">
        <ul className="space-y-1">
          {Object.entries(candidate.score_breakdown).map(([key, value]) => (
            <li key={key} className="flex justify-between gap-4">
              <span className="text-gray-500">{SCORE_LABELS[key] ?? key}</span>
              <span className="font-mono">{value.toFixed(2)}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function CandidatesPage() {
  const [date, setDate] = useState(todayIso());
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchCandidates(date)
      .then((res) => {
        if (!cancelled) setCandidates(res.items);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "候補の取得に失敗しました");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [date]);

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-4 text-xl font-bold">当日候補一覧</h1>
      <div className="mb-4 flex items-center gap-2">
        <label htmlFor="candidate-date" className="text-sm text-gray-600">
          対象日
        </label>
        <input
          id="candidate-date"
          type="date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>

      {loading && <p className="text-sm text-gray-500">読み込み中...</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {!loading && !error && candidates.length === 0 && (
        <p className="text-sm text-gray-500">この日の候補はありません</p>
      )}

      {!loading && candidates.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-gray-500">
                <th className="px-4 py-2 font-medium">商品名</th>
                <th className="px-4 py-2 font-medium">ジャンル</th>
                <th className="px-4 py-2 font-medium">ショップ</th>
                <th className="px-4 py-2 font-medium">スコア</th>
                <th className="px-4 py-2 font-medium">状態</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((candidate) => (
                <tr key={candidate.id} className="border-b border-gray-100 last:border-0">
                  <td className="px-4 py-2">
                    <a
                      href={candidate.item_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-600 hover:underline"
                    >
                      {candidate.product_name}
                    </a>
                  </td>
                  <td className="px-4 py-2">{candidate.genre_name}</td>
                  <td className="px-4 py-2">{candidate.shop_name}</td>
                  <td className="px-4 py-2">
                    <ScoreCell candidate={candidate} />
                  </td>
                  <td className="px-4 py-2">{candidate.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
