import Link from "next/link";

const LINKS = [
  { href: "/candidates", label: "候補一覧" },
  { href: "/review", label: "レビュー" },
  { href: "/queue", label: "投稿キュー" },
];

export function NavBar() {
  return (
    <header className="border-b border-gray-200 bg-white">
      <nav className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-3">
        <span className="text-sm font-semibold text-gray-800">
          Shopping SNS Auto Operation
        </span>
        <ul className="flex gap-4 text-sm">
          {LINKS.map((link) => (
            <li key={link.href}>
              <Link href={link.href} className="text-gray-600 hover:text-blue-600">
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
