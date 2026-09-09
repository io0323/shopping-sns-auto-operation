"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  type Candidate,
  type Content,
  type ContentUpdatePayload,
  type ManualContentResult,
  approveContent,
  createManualContent,
  fetchCandidates,
  fetchContents,
  rejectContent,
  updateContent,
} from "@/lib/api";
import { todayIso } from "@/lib/date";

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

function sameHashtags(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((tag, index) => tag === b[index]);
}

function diffDraft(content: Content, draft: Draft): ContentUpdatePayload {
  const payload: ContentUpdatePayload = {};
  if (draft.title !== content.title) payload.title = draft.title;
  if (draft.description !== content.description) payload.description = draft.description;
  if (!sameHashtags(draft.hashtags, content.hashtags)) payload.hashtags = draft.hashtags;
  if (draft.x_post !== content.x_post) payload.x_post = draft.x_post;
  if (draft.cta !== content.cta) payload.cta = draft.cta;
  return payload;
}

function ManualImportPanel({ onImported }: { onImported: () => void }) {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [candidateId, setCandidateId] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ManualContentResult | null>(null);

  useEffect(() => {
    fetchCandidates(todayIso())
      .then((res) => setCandidates(res.items))
      .catch(() => setCandidates([]));
  }, []);

  const handleImport = async () => {
    if (!candidateId || !text.trim()) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const imported = await createManualContent(candidateId, text);
      setResult(imported);
      setText("");
      onImported();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "取り込みに失敗しました");
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="mb-6 rounded-lg border border-gray-200 bg-white p-4">
      <summary className="cursor-pointer text-sm font-semibold text-gray-700">
        手動生成結果を貼り付け
      </summary>
      <p className="mt-2 text-xs text-gray-500">
        候補一覧で「プロンプトをコピー」したものをチャットUIへ貼り、返ってきたJSONをここに貼り付けます。
        コードフェンス(```)付きのままでも取り込めます。
      </p>

      <label className="mt-3 block text-xs text-gray-600" htmlFor="manual-candidate">
        対象の候補
      </label>
      <select
        id="manual-candidate"
        value={candidateId}
        onChange={(e) => setCandidateId(e.target.value)}
        className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
      >
        <option value="">選択してください</option>
        {candidates.map((candidate) => (
          <option key={candidate.id} value={candidate.id}>
            {candidate.product_name}
          </option>
        ))}
      </select>

      <label className="mt-3 block text-xs text-gray-600" htmlFor="manual-json">
        生成結果のJSON
      </label>
      <textarea
        id="manual-json"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={8}
        placeholder={'{"title": "...", "description": "...", "hashtags": [...], "x_post": "...", "cta": "..."}'}
        className="mt-1 w-full rounded border border-gray-300 px-2 py-1 font-mono text-xs"
      />

      <button
        type="button"
        onClick={handleImport}
        disabled={busy || !candidateId || !text.trim()}
        className="mt-3 rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-500 disabled:opacity-50"
      >
        {busy ? "取り込み中..." : "取り込む"}
      </button>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {result && (
        <div className="mt-3 rounded border border-gray-200 bg-gray-50 p-3 text-xs">
          <p className="font-semibold text-gray-700">
            取り込みました(status: {result.status} / {result.prompt_version} / 手動生成)
          </p>
          {result.rule_violations.length === 0 ? (
            <p className="mt-1 text-green-700">ルールベースチェック: 違反なし</p>
          ) : (
            <div className="mt-1">
              <p className="text-red-600">
                ルールベースチェック: {result.rule_violations.length}件の違反
              </p>
              <ul className="mt-1 list-inside list-disc space-y-0.5 text-red-600">
                {result.rule_violations.map((violation) => (
                  <li key={violation}>{violation}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="mt-1 text-gray-500">
            LLM評価は行っていないため、下の一覧で内容を確認してから承認してください。
          </p>
        </div>
      )}
    </details>
  );
}

export default function ReviewPage() {
  const [contents, setContents] = useState<Content[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
    fetchContents(["evaluated", "needs_review"], "-created_at")
      .then((res) => {
        if (!mountedRef.current) return;
        setContents(res.items);
        const nextDrafts: Record<string, Draft> = {};
        res.items.forEach((content) => {
          nextDrafts[content.id] = toDraft(content);
        });
        setDrafts(nextDrafts);
      })
      .catch((err: unknown) => {
        if (!mountedRef.current) return;
        setError(err instanceof ApiError ? err.message : "コンテンツの取得に失敗しました");
      })
      .finally(() => {
        if (mountedRef.current) setLoading(false);
      });
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
      if (mountedRef.current) {
        setError(err instanceof ApiError ? err.message : failMessage);
      }
    } finally {
      if (mountedRef.current) setBusyId(null);
    }
  };

  const handleSave = (content: Content, draft: Draft) => {
    const payload = diffDraft(content, draft);
    if (Object.keys(payload).length === 0) return;
    withBusy(content.id, () => updateContent(content.id, payload), "保存に失敗しました");
  };

  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-bold">レビュー</h1>
      <ManualImportPanel onImported={load} />
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
                <div className="flex items-center gap-2">
                  {content.generation_source === "manual" && (
                    <span className="rounded bg-purple-100 px-2 py-0.5 text-xs text-purple-700">
                      手動生成
                    </span>
                  )}
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
                  onClick={() => handleSave(content, draft)}
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
