"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type ExportItem, fetchExportQueue, markContentPosted } from "@/lib/api";

function formatScheduledAt(value: string | null): string {
  if (!value) return "未設定";
  return new Date(value).toLocaleString("ja-JP");
}

export default function QueuePage() {
  const [items, setItems] = useState<ExportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchExportQueue()
      .then((res) => {
        if (mountedRef.current) setItems(res.items);
      })
      .catch((err: unknown) => {
        if (mountedRef.current) {
          setError(err instanceof ApiError ? err.message : "取得に失敗しました");
        }
      })
      .finally(() => {
        if (mountedRef.current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCopy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      if (!mountedRef.current) return;
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((current) => (current === key ? null : current)), 2000);
    } catch {
      if (mountedRef.current) setError("クリップボードへのコピーに失敗しました");
    }
  };

  const handleMarkPosted = async (contentId: string) => {
    setBusyId(contentId);
    setError(null);
    try {
      await markContentPosted(contentId);
      load();
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof ApiError ? err.message : "投稿完了マークに失敗しました");
      }
    } finally {
      if (mountedRef.current) setBusyId(null);
    }
  };

  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-bold">投稿キュー</h1>
      {loading && <p className="text-sm text-gray-500">読み込み中...</p>}
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
      {!loading && items.length === 0 && (
        <p className="text-sm text-gray-500">承認済みの投稿はありません</p>
      )}

      <div className="space-y-4">
        {items.map((item) => {
          const roomKey = `${item.content_id}-room`;
          const xKey = `${item.content_id}-x`;
          const busy = busyId === item.content_id;
          return (
            <div key={item.content_id} className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
                <span>{item.product_name}</span>
                <span>投稿予定: {formatScheduledAt(item.scheduled_at)}</span>
              </div>

              {!item.has_ad_disclosure && (
                <p className="mb-2 rounded bg-red-50 px-2 py-1 text-xs text-red-600">
                  X投稿文に #ad 表記がありません。投稿前に確認してください
                </p>
              )}

              <div className="mb-3 grid gap-3 sm:grid-cols-2">
                <div className="rounded border border-gray-100 bg-gray-50 p-2">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-600">ROOM用</span>
                    <button
                      type="button"
                      onClick={() => handleCopy(roomKey, item.room_text)}
                      className="rounded bg-gray-700 px-2 py-1 text-xs text-white"
                    >
                      {copiedKey === roomKey ? "コピーしました" : "コピー"}
                    </button>
                  </div>
                  <p className="whitespace-pre-wrap text-xs text-gray-700">{item.room_text}</p>
                </div>
                <div className="rounded border border-gray-100 bg-gray-50 p-2">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-600">X用</span>
                    <button
                      type="button"
                      onClick={() => handleCopy(xKey, item.x_text)}
                      className="rounded bg-gray-700 px-2 py-1 text-xs text-white"
                    >
                      {copiedKey === xKey ? "コピーしました" : "コピー"}
                    </button>
                  </div>
                  <p className="whitespace-pre-wrap text-xs text-gray-700">{item.x_text}</p>
                </div>
              </div>

              <ul className="mb-3 space-y-1 text-xs text-gray-500">
                {item.checklist.map((check) => (
                  <li key={check} className="flex items-start gap-1">
                    <span>□</span>
                    <span>{check}</span>
                  </li>
                ))}
              </ul>

              <button
                type="button"
                disabled={busy}
                onClick={() => handleMarkPosted(item.content_id)}
                className="rounded bg-green-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
              >
                投稿完了にする
              </button>
            </div>
          );
        })}
      </div>
    </main>
  );
}
