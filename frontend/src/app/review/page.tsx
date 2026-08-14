"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/app-shell";
import { API_BASE_URL, apiRequest } from "@/lib/api";
import { fieldStatusMeta, ReviewTask, taskStatusMeta, TaskStatus } from "@/lib/review-data";

type Filter = "all" | TaskStatus;

export default function ReviewPage() {
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [batchId, setBatchId] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function loadTasks() {
      try {
        const data = await apiRequest<ReviewTask[]>("/api/review-tasks");
        if (!active) return;
        setTasks(data);
        setError("");
        if (data.some((task) => task.status === "analyzing")) {
          timer = setTimeout(loadTasks, 3000);
        }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "审核任务加载失败");
      } finally {
        if (active) setLoading(false);
      }
    }
    loadTasks();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, []);

  const batches = useMemo(() => [...new Set(tasks.map((task) => task.batchId))], [tasks]);
  const filtered = useMemo(() => tasks.filter((task) => {
    const needle = query.trim().toLowerCase();
    return (filter === "all" || task.status === filter) && (batchId === "all" || task.batchId === Number(batchId)) && (!needle || [task.store, task.customerId, task.visitor].some((value) => value.toLowerCase().includes(needle)));
  }), [tasks, filter, batchId, query]);

  const totals = useMemo(() => tasks.reduce((sum, task) => ({ matched: sum.matched + task.stats.matched, pending: sum.pending + task.stats.pending, conflict: sum.conflict + task.stats.conflict, missing: sum.missing + task.stats.missing }), { matched: 0, pending: 0, conflict: 0, missing: 0 }), [tasks]);

  return <AppShell active="review"><main className="mx-auto max-w-[1400px] px-5 py-8 sm:px-8">
    <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between"><div><p className="text-xs font-black tracking-[0.2em] text-[#137161]">REVIEW COMMAND CENTER</p><h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">经理审核工作台</h1><p className="mt-2 text-slate-500">按批次发现风险、处理冲突，并沉淀最终可信数据。</p></div><a href={`${API_BASE_URL}/api/review-tasks/export`} className="rounded-xl bg-[#0d5b4f] px-5 py-3 text-center text-sm font-black text-white hover:bg-[#137161]">↓ 导出审核结果</a></div>

    {error && <div role="alert" className="mt-5 flex justify-between rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700"><span>{error}</span><button onClick={() => setError("")}>×</button></div>}

    <section className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{(["matched", "pending", "conflict", "missing"] as const).map((key) => <div key={key} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><span className="text-sm font-bold text-slate-500">{fieldStatusMeta[key].label}字段</span><span className={`h-2.5 w-2.5 rounded-full ${fieldStatusMeta[key].dot}`}/></div><p className="mt-3 text-3xl font-black tabular-nums">{totals[key]}</p><p className="mt-1 text-xs text-slate-400">当前全部批次</p></div>)}</section>

    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div className="grid gap-3 lg:grid-cols-[1fr_auto_auto]"><label className="relative"><span className="sr-only">搜索任务</span><span className="absolute left-3 top-2.5 text-slate-400">⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索门店名称、门店 ID 或拜访人" className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-3 text-sm outline-none focus:border-[#137161]"/></label><select value={batchId} onChange={(event) => setBatchId(event.target.value)} className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold outline-none"><option value="all">全部批次</option>{batches.map((id) => <option key={id} value={id}>批次 #{id}</option>)}</select><div className="flex overflow-x-auto rounded-xl bg-slate-100 p-1">{(["all", "analyzing", "analysis_failed", "pending", "reviewing", "completed"] as Filter[]).map((item) => <button key={item} onClick={() => setFilter(item)} className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm font-bold ${filter === item ? "bg-white text-[#0d5b4f] shadow-sm" : "text-slate-500"}`}>{item === "all" ? "全部" : taskStatusMeta[item].label}</button>)}</div></div></section>

    <div className="mt-5 flex items-center justify-between text-sm text-slate-500"><span>显示 <strong className="text-slate-900">{filtered.length}</strong> / {tasks.length} 条任务</span><span>更新时间倒序</span></div>

    {loading ? <div className="mt-4 space-y-3" aria-label="加载中">{[1,2,3].map((item) => <div key={item} className="h-32 animate-pulse rounded-2xl bg-slate-200"/>)}</div> : filtered.length === 0 ? <section className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white py-16 text-center"><p className="text-3xl">⌕</p><h2 className="mt-3 font-black">没有找到匹配任务</h2><p className="mt-1 text-sm text-slate-500">尝试清除搜索词或切换审核状态。</p><button onClick={() => { setQuery(""); setFilter("all"); setBatchId("all"); }} className="mt-4 text-sm font-bold text-[#137161]">重置筛选</button></section> : <div className="mt-4 space-y-3">{filtered.map((task, index) => <Link href={`/review/${task.id}`} key={task.id} className="group block rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-[#70a89e] hover:shadow-md"><div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-4"><span aria-label={`第 ${index + 1} 条任务`} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#eaf5f1] text-sm font-black tabular-nums text-[#0d5b4f]">{String(index + 1).padStart(2, "0")}</span><div className="grid min-w-0 gap-5 lg:grid-cols-[1.2fr_.8fr_auto] lg:items-center"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="truncate text-lg font-black">{task.store}</h2><span className={`rounded-full px-2.5 py-1 text-xs font-black ring-1 ${taskStatusMeta[task.status].className}`}>{taskStatusMeta[task.status].label}</span></div><p className="mt-2 text-sm text-slate-500">{task.visitor} · Customer ID {task.customerId}</p><p className="mt-1 text-xs text-slate-400">批次 #{task.batchId} · 任务 #{task.id} · 更新于 {task.updatedAt}</p></div><div className="grid grid-cols-4 gap-2">{(["matched", "pending", "conflict", "missing"] as const).map((key) => <div key={key} className={`rounded-xl px-2 py-3 text-center ${fieldStatusMeta[key].className}`}><p className="text-lg font-black tabular-nums">{task.stats[key]}</p><p className="text-[10px] font-bold">{fieldStatusMeta[key].label}</p></div>)}</div><span className="text-sm font-black text-[#137161] group-hover:translate-x-1">进入审核 →</span></div></div></Link>)}</div>}
  </main></AppShell>;
}
