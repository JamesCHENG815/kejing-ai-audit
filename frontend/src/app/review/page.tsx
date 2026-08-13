import Link from "next/link";

const tasks = [
  { id: "TASK-20260813-001", store: "风筝酒业", visitor: "谭竞锋（佛山）", recordings: 2, conflicts: 1 },
  { id: "TASK-20260813-002", store: "品惠行烟酒（天景大厦店）", visitor: "郑之源（广州）", recordings: 1, conflicts: 2 },
  { id: "TASK-20260813-003", store: "宜嘉真烟酒行（恒福新里程分店）", visitor: "谭竞锋（佛山）", recordings: 2, conflicts: 1 },
];

export default function ReviewPage() {
  return <main className="min-h-screen bg-[#f4f7f9] px-5 py-10 text-slate-900 sm:px-8"><div className="mx-auto max-w-5xl"><p className="text-sm font-semibold tracking-[0.16em] text-teal-700">KEJING AI AUDIT</p><h1 className="mt-2 text-3xl font-bold">待审核任务</h1><p className="mt-2 text-slate-500">选择任务进入经理人工审核详情。</p><div className="mt-7 space-y-3">{tasks.map((task) => <Link key={task.id} href={`/review/${task.id}`} className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-teal-400 hover:shadow-md sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-bold">{task.store}</h2><p className="mt-1 text-sm text-slate-500">{task.visitor} · {task.recordings} 段录音 · {task.id}</p></div><div className="flex items-center gap-3"><span className="rounded-full bg-rose-100 px-3 py-1 text-xs font-bold text-rose-700">{task.conflicts} 项冲突</span><span className="font-semibold text-teal-700">开始审核 →</span></div></Link>)}</div></div></main>;
}
