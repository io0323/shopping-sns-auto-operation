"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type LearningReport, activatePrompt, fetchLearningReport } from "@/lib/api";

function PatternList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold text-gray-600">{title}</h3>
      <ul className="list-inside list-disc space-y-1 text-sm text-gray-700">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export default function LearningReportPage() {
  const [report, setReport] = useState<LearningReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activating, setActivating] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchLearningReport()
      .then((res) => {
        if (mountedRef.current) setReport(res);
      })
      .catch((err: unknown) => {
        if (mountedRef.current) {
          setError(err instanceof ApiError ? err.message : "レポートの取得に失敗しました");
        }
      })
      .finally(() => {
        if (mountedRef.current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleActivate = async () => {
    if (!report?.proposed_prompt_version) return;
    setActivating(true);
    setError(null);
    try {
      await activatePrompt("generator", report.proposed_prompt_version.id);
      load();
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof ApiError ? err.message : "承認に失敗しました");
      }
    } finally {
      if (mountedRef.current) setActivating(false);
    }
  };

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="mb-4 text-xl font-bold">週次学習レポート</h1>
      {loading && <p className="text-sm text-gray-500">読み込み中...</p>}
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {!loading && report?.status === "no_report" && (
        <p className="text-sm text-gray-500">まだレポートが生成されていません</p>
      )}

      {!loading && report?.status === "insufficient_data" && (
        <p className="text-sm text-gray-500">
          実績データが{report.data_point_count}件のため、分析をスキップしました
          (30件以上で分析を開始します)
        </p>
      )}

      {!loading && report?.status === "budget_exceeded" && (
        <p className="text-sm text-amber-600">
          月間LLM予算の上限に達したため、今回の学習はスキップされました
        </p>
      )}

      {!loading && report?.status === "invalid_llm_response" && (
        <p className="text-sm text-amber-600">
          Learning Agentの応答を解析できなかったため、今回の改善提案はスキップされました
        </p>
      )}

      {!loading && report?.status === "completed" && report.report && (
        <div className="space-y-6">
          {report.run_date && (
            <p className="text-xs text-gray-400">
              実行日: {report.run_date} / 分析対象: {report.data_point_count}件
            </p>
          )}

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold text-gray-700">サマリー</h2>
            <p className="text-sm text-gray-700">{report.report.summary}</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <PatternList title="高成果群の特徴" items={report.report.high_performer_patterns} />
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4">
              <PatternList title="低成果群の特徴" items={report.report.low_performer_patterns} />
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <PatternList title="改善の推奨事項" items={report.report.recommendations} />
          </div>

          {report.proposed_prompt_version && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-gray-700">
                  Generatorプロンプト改善案({report.proposed_prompt_version.version})
                </h2>
                {report.proposed_prompt_version.is_active ? (
                  <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">
                    有効化済み
                  </span>
                ) : (
                  <button
                    type="button"
                    disabled={activating}
                    onClick={handleActivate}
                    className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
                  >
                    承認して有効化
                  </button>
                )}
              </div>
              {report.proposed_prompt_version.note && (
                <p className="mb-2 text-xs text-gray-600">
                  根拠: {report.proposed_prompt_version.note}
                </p>
              )}
              <pre className="whitespace-pre-wrap rounded bg-white p-3 text-xs text-gray-700">
                {report.proposed_prompt_version.body}
              </pre>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
