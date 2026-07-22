"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, type Content, fetchContents, markContentPosted } from "@/lib/api";

function buildRoomText(content: Content): string {
  return [content.title, content.description, content.hashtags.join(" ")].join("\n\n");
}

function formatScheduledAt(value: string | null): string {
  if (!value) return "未設定";
  return new Date(value).toLocaleString("ja-JP");
}

export default function QueuePage() {
  const [contents, setContents] = useState<Content[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchContents(["approved"], "scheduled_at")
      .then((res) => setContents(res.items))
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "取得に失敗しました");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCopy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((current) => (current === key ? null : current)), 2000);
    } catch {
      setError("クリップボードへのコピーに失敗しました");
    }
  };

  const handleMarkPosted = async (id: string) => {
    setBusyId(id);
    setError(null);
    try {
      await markContentPosted(id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "投稿完了マークに失敗しました");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-bold">投稿キュー</h1>
      {loading && <p className="text-sm text-gray-500">読み込み中...</p>}
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
      {!loading && contents.length === 0 && (
        <p className="text-sm text-gray-500">承認済みの投稿はありません</p>
      )}

      <div className="space-y-4">
        {contents.map((content) => {
          const roomKey = `${content.id}-room`;
          const xKey = `${content.id}-x`;
          const busy = busyId === content.id;
          return (
            <div key={content.id} className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
                <span>{content.product_name}</span>
                <span>投稿予定: {formatScheduledAt(content.scheduled_at)}</span>
              </div>

              <div className="mb-3 grid gap-3 sm:grid-cols-2">
                <div className="rounded border border-gray-100 bg-gray-50 p-2">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-600">ROOM用</span>
                    <button
                      type="button"
                      onClick={() => handleCopy(roomKey, buildRoomText(content))}
                      className="rounded bg-gray-700 px-2 py-1 text-xs text-white"
                    >
                      {copiedKey === roomKey ? "コピーしました" : "コピー"}
                    </button>
                  </div>
                  <p className="whitespace-pre-wrap text-xs text-gray-700">
                    {buildRoomText(content)}
                  </p>
                </div>
                <div className="rounded border border-gray-100 bg-gray-50 p-2">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-600">X用</span>
                    <button
                      type="button"
                      onClick={() => handleCopy(xKey, content.x_post)}
                      className="rounded bg-gray-700 px-2 py-1 text-xs text-white"
                    >
                      {copiedKey === xKey ? "コピーしました" : "コピー"}
                    </button>
                  </div>
                  <p className="whitespace-pre-wrap text-xs text-gray-700">{content.x_post}</p>
                </div>
              </div>

              <button
                type="button"
                disabled={busy}
                onClick={() => handleMarkPosted(content.id)}
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
