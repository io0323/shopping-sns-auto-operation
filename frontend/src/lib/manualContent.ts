/**
 * 手動生成結果の入力フォーム用ロジック。
 *
 * 文字数・個数の上限はバックエンド(app/agents/generator.py)の定数と同じ値を持つが、
 * これは入力中に体裁を示すための補助であり、保存可否の判定はサーバー側の
 * ルールベースチェックが行う(こちらが正)。
 *
 * 禁止表現(ng_words.yaml)の判定はここに持たない。辞書を二重管理しないため、
 * NGワード検出はサーバー側だけで行い、結果を取り込み後に表示する。
 */

export const LIMITS = {
  titleMax: 30,
  descriptionMin: 80,
  descriptionMax: 150,
  hashtagsMin: 5,
  hashtagsMax: 8,
  xPostMax: 120,
  ctaMax: 20,
} as const;

export interface ManualContentForm {
  title: string;
  description: string;
  hashtags: string;
  x_post: string;
  cta: string;
}

export interface ManualContentPayload {
  title: string;
  description: string;
  hashtags: string[];
  x_post: string;
  cta: string;
}

export const EMPTY_FORM: ManualContentForm = {
  title: "",
  description: "",
  hashtags: "",
  x_post: "",
  cta: "",
};

const SEPARATORS = /[\s,、，]+/;
const LEADING_HASH = /^[#＃]+/;

/**
 * ハッシュタグ入力を配列へ変換する。
 *
 * スペース・カンマ(半角/全角)・読点のいずれの区切りも受け付け、入力側の
 * 「#」の有無は問わない。保存時は常に「#」付きへ揃える。
 */
export function parseHashtags(input: string): string[] {
  return input
    .split(SEPARATORS)
    .map((tag) => tag.replace(LEADING_HASH, "").trim())
    .filter((tag) => tag.length > 0)
    .map((tag) => `#${tag}`);
}

/** フォームの値をAPI(`POST /candidates/{id}/manual-content`)のcontent JSONへ組み立てる。 */
export function buildManualContentPayload(form: ManualContentForm): ManualContentPayload {
  return {
    title: form.title.trim(),
    description: form.description.trim(),
    hashtags: parseHashtags(form.hashtags),
    x_post: form.x_post.trim(),
    cta: form.cta.trim(),
  };
}

/** コードフェンス(```json ... ```)が付いていれば取り除く。 */
export function stripCodeFence(text: string): string {
  const trimmed = text.trim();
  const match = /^```(?:json)?\s*([\s\S]*?)\s*```$/.exec(trimmed);
  return match ? match[1] : trimmed;
}

export type JsonToFormResult =
  | { ok: true; form: ManualContentForm; missing: string[] }
  | { ok: false; error: string };

const FIELD_KEYS = ["title", "description", "hashtags", "x_post", "cta"] as const;

/**
 * 貼り付けられたJSONをフォームの初期値へ変換する。
 *
 * ここでは保存せず入力欄を埋めるだけなので、欠けているフィールドがあっても
 * 失敗にはせず、埋められた分だけ反映して`missing`で知らせる。
 */
export function formFromJson(text: string): JsonToFormResult {
  const raw = stripCodeFence(text);
  if (!raw.trim()) {
    return { ok: false, error: "JSONが空です" };
  }

  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return { ok: false, error: "JSONとして解釈できません" };
  }

  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return { ok: false, error: "JSONオブジェクト({...})である必要があります" };
  }

  const record = data as Record<string, unknown>;
  const form: ManualContentForm = { ...EMPTY_FORM };
  const missing: string[] = [];

  for (const key of FIELD_KEYS) {
    const value = record[key];
    if (value === undefined || value === null) {
      missing.push(key);
      continue;
    }
    if (key === "hashtags") {
      form.hashtags = Array.isArray(value)
        ? value.map((tag) => String(tag)).join(" ")
        : String(value);
      continue;
    }
    form[key] = String(value);
  }

  return { ok: true, form, missing };
}

export interface FieldStatus {
  count: number;
  ok: boolean;
  label: string;
}

/** 入力中に各欄へ出す「現在値 / 制約」の表示内容。 */
export function fieldStatuses(form: ManualContentForm): Record<string, FieldStatus> {
  const title = form.title.trim().length;
  const description = form.description.trim().length;
  const tags = parseHashtags(form.hashtags).length;
  const xPost = form.x_post.trim().length;
  const cta = form.cta.trim().length;

  return {
    title: {
      count: title,
      ok: title > 0 && title <= LIMITS.titleMax,
      label: `${title} / ${LIMITS.titleMax}文字`,
    },
    description: {
      count: description,
      ok: description >= LIMITS.descriptionMin && description <= LIMITS.descriptionMax,
      label: `${description} / ${LIMITS.descriptionMin}〜${LIMITS.descriptionMax}文字`,
    },
    hashtags: {
      count: tags,
      ok: tags >= LIMITS.hashtagsMin && tags <= LIMITS.hashtagsMax,
      label: `${tags} / ${LIMITS.hashtagsMin}〜${LIMITS.hashtagsMax}個`,
    },
    x_post: {
      count: xPost,
      ok: xPost > 0 && xPost <= LIMITS.xPostMax,
      label: `${xPost} / ${LIMITS.xPostMax}文字`,
    },
    cta: {
      count: cta,
      ok: cta > 0 && cta <= LIMITS.ctaMax,
      label: `${cta} / ${LIMITS.ctaMax}文字`,
    },
  };
}

/** X投稿文に #ad が含まれているか(サーバー側チェックの先出し表示用)。 */
export function hasAdDisclosure(xPost: string): boolean {
  return xPost.includes("#ad");
}

/** 必須項目が埋まっているか(送信ボタンの活性判定用。内容の妥当性は見ない)。 */
export function isSubmittable(form: ManualContentForm): boolean {
  const payload = buildManualContentPayload(form);
  return (
    payload.title.length > 0 &&
    payload.description.length > 0 &&
    payload.hashtags.length > 0 &&
    payload.x_post.length > 0 &&
    payload.cta.length > 0
  );
}
