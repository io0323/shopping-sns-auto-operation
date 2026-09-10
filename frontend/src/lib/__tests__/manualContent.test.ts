import { describe, expect, it } from "vitest";

import {
  EMPTY_FORM,
  buildManualContentPayload,
  fieldStatuses,
  formFromJson,
  hasAdDisclosure,
  isSubmittable,
  parseHashtags,
  stripCodeFence,
} from "../manualContent";

describe("parseHashtags", () => {
  it("スペース区切りを配列化して#を付ける", () => {
    expect(parseHashtags("水筒 ステンレスボトル 通勤")).toEqual([
      "#水筒",
      "#ステンレスボトル",
      "#通勤",
    ]);
  });

  it("カンマ区切り(半角・全角)と読点を受け付ける", () => {
    expect(parseHashtags("水筒,通勤，時短、ギフト")).toEqual([
      "#水筒",
      "#通勤",
      "#時短",
      "#ギフト",
    ]);
  });

  it("#の有無が混在していても重複して付けない", () => {
    expect(parseHashtags("#水筒 通勤 ＃楽天ROOM")).toEqual(["#水筒", "#通勤", "#楽天ROOM"]);
  });

  it("区切りが連続していても空要素を作らない", () => {
    expect(parseHashtags("  水筒 ,,  通勤  ")).toEqual(["#水筒", "#通勤"]);
  });

  it("空文字は空配列になる", () => {
    expect(parseHashtags("")).toEqual([]);
    expect(parseHashtags("   ")).toEqual([]);
  });

  it("先頭の#が複数あっても1つに揃える", () => {
    expect(parseHashtags("##水筒")).toEqual(["#水筒"]);
  });
});

describe("buildManualContentPayload", () => {
  it("APIへ送るJSONの形になる(hashtagsは配列)", () => {
    const payload = buildManualContentPayload({
      title: "  タイトル  ",
      description: " 説明文 ",
      hashtags: "水筒, 通勤",
      x_post: " 投稿文 #ad ",
      cta: " 商品ページで確認 ",
    });

    expect(payload).toEqual({
      title: "タイトル",
      description: "説明文",
      hashtags: ["#水筒", "#通勤"],
      x_post: "投稿文 #ad",
      cta: "商品ページで確認",
    });
    expect(Array.isArray(payload.hashtags)).toBe(true);
  });

  it("APIの契約(5フィールド)以外を含まない", () => {
    const payload = buildManualContentPayload({ ...EMPTY_FORM, title: "a" });
    expect(Object.keys(payload).sort()).toEqual([
      "cta",
      "description",
      "hashtags",
      "title",
      "x_post",
    ]);
  });
});

describe("stripCodeFence", () => {
  it("```json 付きを剥がす", () => {
    expect(stripCodeFence('```json\n{"a":1}\n```')).toBe('{"a":1}');
  });

  it("言語指定なしのフェンスも剥がす", () => {
    expect(stripCodeFence('```\n{"a":1}\n```')).toBe('{"a":1}');
  });

  it("フェンスが無ければそのまま返す", () => {
    expect(stripCodeFence(' {"a":1} ')).toBe('{"a":1}');
  });
});

describe("formFromJson", () => {
  const valid = {
    title: "タイトル",
    description: "説明文",
    hashtags: ["#水筒", "通勤"],
    x_post: "投稿文 #ad",
    cta: "商品ページで確認",
  };

  it("JSONを各入力欄の値へ流し込む", () => {
    const result = formFromJson(JSON.stringify(valid));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.form.title).toBe("タイトル");
    // 配列はスペース区切りの1行として入力欄へ入れる
    expect(result.form.hashtags).toBe("#水筒 通勤");
    expect(result.missing).toEqual([]);
  });

  it("コードフェンス付きのまま貼られても反映できる", () => {
    const result = formFromJson("```json\n" + JSON.stringify(valid) + "\n```");
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.form.cta).toBe("商品ページで確認");
  });

  it("反映後のフォームからそのままAPIペイロードを組み立てられる", () => {
    const result = formFromJson(JSON.stringify(valid));
    if (!result.ok) throw new Error("parse failed");
    expect(buildManualContentPayload(result.form).hashtags).toEqual(["#水筒", "#通勤"]);
  });

  it("欠けたフィールドは失敗にせずmissingで知らせる", () => {
    const partial: Record<string, unknown> = { ...valid };
    delete partial.hashtags;
    delete partial.cta;
    const result = formFromJson(JSON.stringify(partial));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.missing.sort()).toEqual(["cta", "hashtags"]);
    expect(result.form.title).toBe("タイトル");
  });

  it("不正なJSONはエラーを返す", () => {
    const result = formFromJson("{title: 壊れている}");
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toContain("JSONとして解釈できません");
  });

  it("配列やスカラーはオブジェクトでないとして弾く", () => {
    expect(formFromJson("[1,2]").ok).toBe(false);
    expect(formFromJson('"文字列"').ok).toBe(false);
  });

  it("空文字はエラーを返す", () => {
    expect(formFromJson("   ").ok).toBe(false);
  });
});

describe("fieldStatuses", () => {
  it("文字数と個数を数え、範囲内かを返す", () => {
    const status = fieldStatuses({
      title: "あ".repeat(10),
      description: "い".repeat(100),
      hashtags: "a b c d e",
      x_post: "う".repeat(50),
      cta: "え".repeat(10),
    });

    expect(status.title).toMatchObject({ count: 10, ok: true });
    expect(status.description).toMatchObject({ count: 100, ok: true });
    expect(status.hashtags).toMatchObject({ count: 5, ok: true });
    expect(status.x_post).toMatchObject({ count: 50, ok: true });
    expect(status.cta).toMatchObject({ count: 10, ok: true });
  });

  it("上限超過・下限未満を検出する", () => {
    const status = fieldStatuses({
      title: "あ".repeat(31),
      description: "い".repeat(79),
      hashtags: "a b c d",
      x_post: "う".repeat(121),
      cta: "え".repeat(21),
    });

    expect(status.title.ok).toBe(false);
    expect(status.description.ok).toBe(false);
    expect(status.hashtags.ok).toBe(false);
    expect(status.x_post.ok).toBe(false);
    expect(status.cta.ok).toBe(false);
  });

  it("表示ラベルに制約を含む", () => {
    const status = fieldStatuses(EMPTY_FORM);
    expect(status.description.label).toBe("0 / 80〜150文字");
    expect(status.hashtags.label).toBe("0 / 5〜8個");
  });
});

describe("hasAdDisclosure", () => {
  it("#ad の有無を判定する", () => {
    expect(hasAdDisclosure("投稿文 #ad")).toBe(true);
    expect(hasAdDisclosure("投稿文")).toBe(false);
  });
});

describe("isSubmittable", () => {
  it("5項目すべて埋まっていれば送信可能", () => {
    expect(
      isSubmittable({
        title: "t",
        description: "d",
        hashtags: "a",
        x_post: "x",
        cta: "c",
      }),
    ).toBe(true);
  });

  it("1つでも空なら送信不可", () => {
    expect(isSubmittable({ ...EMPTY_FORM, title: "t" })).toBe(false);
  });
});
