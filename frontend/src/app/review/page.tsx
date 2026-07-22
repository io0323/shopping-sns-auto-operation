"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  type Content,
  approveContent,
  fetchContents,
  rejectContent,
  updateContent,
} from "@/lib/api";

const QUALITY_LABELS: Record<string, string> = {
  natural: "自然さ",
  readability: "可読性",
  appeal: "訴求力",
  uniqueness: "独自性",
  compliance: "規約適合",
};

interface Draft {
  title: string;
  description: string;
  hashtags: string[];
  x_post: string;
  cta: string;
}

function toDraft(content: Content): Draft {
  return {
    title: content.title,
    description: content.description,
    hashtags: content.hashtags,
    x_post: content.x_post,
    cta: content.cta,
  };
}

export default function ReviewPage() {
  const [contents, setContents] = useState<Content[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchContents(["evaluated", "needs_review"], "-created_at")
      .then((res) => {
        setContents(res.items);
        const nextDrafts: Record<string, Draft> = {};
        res.items.forEach((content) => {
          nextDrafts[content.id] = toDraft(content);
        });
        setDrafts(nextDrafts);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "コンテンツの取得に失敗しました");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const updateDraft = (id: string, field: keyof Draft, value: string) => {
    setDrafts((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        [field]: field === "hashtags" ? value.split(/\s+/).filter(Boolean) : value,
      },
    }));
  };

  const withBusy = async (id: string, action: () => Promise<Content>, failMessage: string) => {
    setBusyId(id);
    setError(null);
    try {
      await action();
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : failMessage);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-bold">レビュー</h1>
      {loading && <p className="text-sm text-gray-500">読み込み中...</p>}
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
      {!loading && contents.length === 0 && (
        <p className="text-sm text-gray-500">レビュー対象のコンテンツはありません</p>
      )}

      <div className="space-y-6">
        {contents.map((content) => {
          const draft = drafts[content.id] ?? toDraft(content);
          const busy = busyId === content.id;
          return (
            <div key={content.id} className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">
                  {content.product_name}
                </span>
                <span
                  className={`rounded px-2 py-0.5 text-xs ${
                    content.status === "needs_review"
                      ? "bg-amber-100 text-amber-700"
                      : "bg-green-100 text-green-700"
                  }`}
                >
                  {content.status}
                </span>
              </div>

              {content.quality_score !== null && (
                <div className="mb-3 flex flex-wrap gap-3 text-xs text-gray-500">
                  <span className="font-semibold text-gray-700">
                    品質スコア: {content.quality_score}
                  </span>
                  {content.quality_breakdown &&
                    Object.entries(content.quality_breakdown).map(([key, value]) => (
                      <span key={key}>
                        {QUALITY_LABELS[key] ?? key}: {value}
                      </span>
                    ))}
                </div>
              )}
              {content.eval_comment && (
                <p className="mb-3 rounded bg-gray-50 p-2 text-xs text-gray-600">
                  評価コメント: {content.eval_comment}
                </p>
              )}

              <div className="space-y-2">
                <label className="block text-xs text-gray-500">
                  タイトル
                  <input
                    className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
                    value={draft.title}
                    onChange={(event) => updateDraft(content.id, "title", event.target.value)}
                  />
                </label>
                <label className="block text-xs text-gray-500">
                  説明文
                  <textarea
                    className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
                    rows={3}
                    value={draft.description}
                    onChange={(event) =>
                      updateDraft(content.id, "description", event.target.value)
                    }
                  />
                </label>
                <label className="block text-xs text-gray-500">
                  ハッシュタグ(スペース区切り)
                  <input
                    className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
                    value={draft.hashtags.join(" ")}
                    onChange={(event) =>
                      updateDraft(content.id, "hashtags", event.target.value)
                    }
                  />
                </label>
                <label className="block text-xs text-gray-500">
                  X投稿文
                  <textarea
                    className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
                    rows={2}
                    value={draft.x_post}
                    onChange={(event) => updateDraft(content.id, "x_post", event.target.value)}
                  />
                </label>
                <label className="block text-xs text-gray-500">
                  CTA
                  <input
                    className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
                    value={draft.cta}
                    onChange={(event) => updateDraft(content.id, "cta", event.target.value)}
                  />
                </label>
              </div>

              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    withBusy(
                      content.id,
                      () => updateContent(content.id, draft),
                      "保存に失敗しました",
                    )
                  }
                  className="rounded bg-gray-700 px-3 py-1.5 text-xs text-white disabled:opacity-50"
                >
                  保存
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    withBusy(content.id, () => approveContent(content.id), "承認に失敗しました")
                  }
                  className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
                >
                  承認
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    withBusy(content.id, () => rejectContent(content.id), "除外に失敗しました")
                  }
                  className="rounded bg-red-600 px-3 py-1.5 text-xs text-white disabled:opacity-50"
                >
                  除外
                </button>
                {content.edited_by_human && (
                  <span className="ml-auto text-xs text-gray-400">編集済み</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </main>
  );
}
