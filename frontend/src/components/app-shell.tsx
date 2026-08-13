import Link from "next/link";

export default function AppShell({
  active,
  children,
}: {
  active: "import" | "review";
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-[#f3f6f5] text-slate-950">
      <header className="border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-5 py-4 sm:px-8">
          <Link href="/" className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#0d5b4f] font-black text-white">客</span>
            <span><span className="block text-sm font-black tracking-[0.16em] text-[#0d5b4f]">客经智审</span><span className="hidden text-[11px] text-slate-400 sm:block">KEJING AI AUDIT</span></span>
          </Link>
          <nav className="flex rounded-xl bg-slate-100 p-1 text-sm font-semibold" aria-label="主导航">
            <Link href="/import" className={`rounded-lg px-4 py-2 transition ${active === "import" ? "bg-white text-[#0d5b4f] shadow-sm" : "text-slate-500 hover:text-slate-900"}`}>数据导入</Link>
            <Link href="/review" className={`rounded-lg px-4 py-2 transition ${active === "review" ? "bg-white text-[#0d5b4f] shadow-sm" : "text-slate-500 hover:text-slate-900"}`}>经理审核</Link>
          </nav>
        </div>
      </header>
      {children}
    </div>
  );
}
