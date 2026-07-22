"use client";

import { useRef, useState } from "react";
import { ApiError, type ImportSummary, uploadAffiliateCsv } from "@/lib/api";

export default function ImportPage() {
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async () => {
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      setError("CSVファイルを選択してください");
      return;
    }

    setUploading(true);
    setError(null);
    try {
      const result = await uploadAffiliateCsv(file);
      setSummary(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "取込に失敗しました");
    } finally {
      setUploading(false);
    }
  };

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="mb-4 text-xl font-bold">アフィリエイト実績CSV取込</h1>
      <p className="mb-4 text-sm text-gray-500">
        楽天アフィリエイト管理画面からダウンロードしたレポートCSV(Shift-JIS)をアップロードしてください。
      </p>

      <div className="mb-4 flex items-center gap-3 rounded-lg border border-gray-200 bg-white p-4">
        <input ref={fileInputRef} type="file" accept=".csv" className="text-sm" />
        <button
          type="button"
          disabled={uploading}
          onClick={handleUpload}
          className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
        >
          {uploading ? "取込中..." : "アップロード"}
        </button>
      </div>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <p className="text-xs text-gray-500">新規取込</p>
              <p className="text-lg font-semibold text-gray-800">{summary.imported}</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <p className="text-xs text-gray-500">上書き</p>
              <p className="text-lg font-semibold text-gray-800">{summary.updated}</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
              <p className="text-xs text-gray-500">エラー</p>
              <p className="text-lg font-semibold text-red-600">{summary.error_count}</p>
            </div>
          </div>

          {summary.errors.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="w-full min-w-[480px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-gray-500">
                    <th className="px-4 py-2 font-medium">行データ</th>
                    <th className="px-4 py-2 font-medium">理由</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.errors.map((row, index) => (
                    <tr key={index} className="border-b border-gray-100 last:border-0">
                      <td className="px-4 py-2 font-mono text-xs text-gray-600">{row.raw_line}</td>
                      <td className="px-4 py-2 text-xs text-red-600">{row.reason}</td>
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
