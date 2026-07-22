import Link from "next/link";

const LINKS = [
  {
    href: "/candidates",
    label: "候補一覧",
    description: "当日のスコア付き投稿候補を確認します",
  },
  {
    href: "/review",
    label: "レビュー",
    description: "生成済みコンテンツの編集・承認・除外を行います",
  },
  {
    href: "/queue",
    label: "投稿キュー",
    description: "承認済みコンテンツをコピーして投稿します",
  },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="mb-2 text-xl font-bold">Shopping SNS Auto Operation</h1>
      <p className="mb-6 text-sm text-gray-500">
        楽天ROOM運用の半自動化システム。投稿操作は必ず人間が行います。
      </p>
      <ul className="grid gap-4 sm:grid-cols-3">
        {LINKS.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              className="block h-full rounded-lg border border-gray-200 bg-white p-4 hover:border-blue-400 hover:shadow-sm"
            >
              <span className="block text-sm font-semibold text-gray-800">
                {link.label}
              </span>
              <span className="mt-1 block text-xs text-gray-500">
                {link.description}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
