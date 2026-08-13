"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { API_BASE_URL, apiRequest } from "@/lib/api";
import { fieldStatusMeta, FieldStatus, reviewTasks, taskStatusMeta } from "@/lib/review-data";

type ReviewField = {
  key: string; label: string; excel: string; ai: string; unit?: string;
  confidence: number; status: FieldStatus; final: string; reason: string; confirmed: boolean;
  evidence?: { recordingId: string; start: number; end: number; text: string };
};
type Recording = { id: string; name: string; duration: number; url?: string };
type Transcript = { recordingId: string; time: number; speaker: string; text: string; evidence?: boolean };
type History = { who: string; when: string; action: string };

const recordings: Recording[] = [
  { id: "REC-001", name: "风筝酒业.m4a", duration: 184, url: `${API_BASE_URL}/storage/recordings/1/${encodeURIComponent("风筝酒业.m4a")}` },
  { id: "REC-002", name: "风筝酒业(1).m4a", duration: 152, url: `${API_BASE_URL}/storage/recordings/1/${encodeURIComponent("风筝酒业(1).m4a")}` },
];
const transcripts: Transcript[] = [
  { recordingId: "REC-001", time: 8, speaker: "业务员", text: "老板您好，今天想了解一下门店今年的销售情况。" },
  { recordingId: "REC-001", time: 34, speaker: "门店", text: "今年到三月底大概卖了八万左右，比去年同期稍好一点。", evidence: true },
  { recordingId: "REC-001", time: 78, speaker: "业务员", text: "马爹利这边去年全年大概是多少？畅销的是哪些产品？" },
  { recordingId: "REC-001", time: 125.2, speaker: "门店", text: "马爹利去年大概二十万，蓝带和名士卖得比较好。", evidence: true },
  { recordingId: "REC-001", time: 143, speaker: "业务员", text: "现在经营上还有什么问题吗？" },
  { recordingId: "REC-001", time: 151, speaker: "门店", text: "主要是客流少了一些，希望活动支持能多一点。", evidence: true },
  { recordingId: "REC-002", time: 12, speaker: "业务员", text: "再确认一下，上个月洋酒大概卖了多少瓶？" },
  { recordingId: "REC-002", time: 20, speaker: "门店", text: "上个月大概一百瓶左右。", evidence: true },
];
const demoFields: ReviewField[] = [
  { key: "lastYearSales", label: "马爹利去年销售额", excel: "25", ai: "20", unit: "万元", confidence: .95, status: "conflict", final: "20", reason: "", confirmed: false, evidence: { recordingId: "REC-001", start: 125.2, end: 131.6, text: "马爹利去年大概二十万" } },
  { key: "salesToMarch", label: "今年截至三月销售额", excel: "20", ai: "20", unit: "万元", confidence: .92, status: "matched", final: "20", reason: "", confirmed: false, evidence: { recordingId: "REC-001", start: 34, end: 41.5, text: "今年到三月底大概卖了八万左右" } },
  { key: "bestSeller", label: "畅销产品", excel: "马爹利名士 1L", ai: "蓝带、名士", confidence: .91, status: "pending", final: "蓝带、名士", reason: "", confirmed: false, evidence: { recordingId: "REC-001", start: 130, end: 136, text: "蓝带和名士卖得比较好" } },
  { key: "lastMonthBottles", label: "上月洋酒销量", excel: "—", ai: "100", unit: "瓶", confidence: .88, status: "missing", final: "100", reason: "", confirmed: false, evidence: { recordingId: "REC-002", start: 20, end: 24, text: "上个月大概一百瓶左右" } },
  { key: "issues", label: "其他经营问题", excel: "—", ai: "客流减少，希望增加活动支持", confidence: .84, status: "missing", final: "客流减少，希望增加活动支持", reason: "", confirmed: false, evidence: { recordingId: "REC-001", start: 151, end: 160, text: "主要是客流少了一些，希望活动支持能多一点" } },
];

function formatTime(value: number) { return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, "0")}`; }
export default function ReviewDetail({ taskId }: { taskId: string }) {
  const task = reviewTasks.find((item) => item.id === taskId) ?? reviewTasks[1];
  const audioRef = useRef<HTMLAudioElement>(null);
  const [activeRecording, setActiveRecording] = useState(recordings[0]);
  const [currentTime, setCurrentTime] = useState(0);
  const [fields, setFields] = useState<ReviewField[]>(demoFields);
  const [history, setHistory] = useState<History[]>([{ who: "AI 系统", when: "2026-08-13 16:36", action: "完成录音字段提取与风险比对" }, { who: "谭经理", when: "2026-08-13 16:39", action: "开始审核任务" }]);
  const [busy, setBusy] = useState<"draft" | "submit" | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem(`review-draft-${taskId}`);
    if (!saved) return;
    const timer = window.setTimeout(() => {
      try {
        setFields(JSON.parse(saved));
        setMessage("已恢复本机保存的审核草稿。");
      } catch {}
    }, 0);
    return () => window.clearTimeout(timer);
  }, [taskId]);

  const confirmedCount = fields.filter((field) => field.confirmed).length;
  const activeTranscript = transcripts.filter((line) => line.recordingId === activeRecording.id);

  function seek(recordingId: string, time: number) {
    const recording = recordings.find((item) => item.id === recordingId) ?? activeRecording;
    setActiveRecording(recording); setCurrentTime(time);
    window.setTimeout(() => { if (audioRef.current) { audioRef.current.currentTime = time; audioRef.current.play().catch(() => undefined); } }, 0);
  }

  function updateField(key: string, patch: Partial<ReviewField>) {
    setFields((current) => current.map((field) => field.key === key ? { ...field, ...patch } : field)); setMessage("");
  }

  function confirmField(field: ReviewField) {
    if (field.final !== field.excel && !field.reason.trim()) return setError(`“${field.label}”修改了原值，请填写修改原因`);
    updateField(field.key, { confirmed: true }); setError("");
  }

  function confirmMatched() {
    setFields((current) => current.map((field) => field.status === "matched" ? { ...field, confirmed: true, final: field.excel } : field));
    setMessage("一致字段已全部确认。");
  }

  async function saveDraft() {
    setBusy("draft"); setError("");
    localStorage.setItem(`review-draft-${taskId}`, JSON.stringify(fields));
    try { await apiRequest(`/api/review-tasks/${taskId}/draft`, { method: "PUT", body: JSON.stringify({ fields }) }); } catch { /* Local fallback until review API is available. */ }
    const item = { who: "当前经理", when: new Date().toLocaleString("zh-CN", { hour12: false }), action: `保存审核草稿，已确认 ${confirmedCount}/${fields.length} 个字段` };
    setHistory((current) => [item, ...current]); setMessage("审核草稿已保存。"); setBusy(null);
  }

  async function submitReview() {
    if (confirmedCount !== fields.length) return setError(`还有 ${fields.length - confirmedCount} 个字段未确认`);
    const invalid = fields.find((field) => field.final !== field.excel && !field.reason.trim());
    if (invalid) return setError(`“${invalid.label}”需要填写修改原因`);
    setBusy("submit"); setError("");
    try { await apiRequest(`/api/review-tasks/${taskId}/submit`, { method: "POST", body: JSON.stringify({ fields }) }); } catch { /* Demo fallback. */ }
    localStorage.removeItem(`review-draft-${taskId}`); setHistory((current) => [{ who: "当前经理", when: new Date().toLocaleString("zh-CN", { hour12: false }), action: "提交并完成审核" }, ...current]); setMessage("审核已提交完成。演示模式下结果保存在当前页面。" ); setBusy(null);
  }

  return <div className="min-h-screen bg-[#f3f6f5] text-slate-950">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-[1600px] flex-col gap-4 px-5 py-5 sm:px-8 lg:flex-row lg:items-center lg:justify-between"><div><Link href="/review" className="text-sm font-bold text-[#137161]">← 返回审核任务</Link><div className="mt-2 flex flex-wrap items-center gap-3"><h1 className="text-2xl font-black">{task.store}</h1><span className={`rounded-full px-3 py-1 text-xs font-black ring-1 ${taskStatusMeta[task.status].className}`}>{taskStatusMeta[task.status].label}</span></div><p className="mt-1 text-sm text-slate-500">任务 #{task.id} · Customer ID {task.customerId} · {task.visitor}</p></div><div className="flex flex-wrap gap-2"><button onClick={() => setShowHistory((value) => !value)} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold">审核历史 {showHistory ? "↑" : "↓"}</button><button onClick={saveDraft} disabled={busy !== null} className="rounded-xl border border-[#0d5b4f] px-4 py-2.5 text-sm font-bold text-[#0d5b4f]">{busy === "draft" ? "保存中…" : "保存草稿"}</button><button onClick={submitReview} disabled={busy !== null} className="rounded-xl bg-[#0d5b4f] px-5 py-2.5 text-sm font-black text-white">{busy === "submit" ? "提交中…" : "提交完成审核"}</button></div></div></header>

    <main className="mx-auto max-w-[1600px] px-5 py-6 sm:px-8">
      {(error || message) && <div className={`mb-5 flex justify-between rounded-xl border px-4 py-3 text-sm font-bold ${error ? "border-rose-200 bg-rose-50 text-rose-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}><span>{error || message}</span><button onClick={() => { setError(""); setMessage(""); }}>×</button></div>}
      {showHistory && <section className="mb-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><h2 className="font-black">审核历史</h2><div className="mt-4 space-y-3">{history.map((item, index) => <div key={`${item.when}-${index}`} className="flex gap-3 text-sm"><span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[#137161]"/><div><p><strong>{item.who}</strong> · {item.action}</p><p className="mt-0.5 text-xs text-slate-400">{item.when}</p></div></div>)}</div></section>}

      <div className="grid gap-5 xl:grid-cols-[390px_minmax(0,1fr)]">
        <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-100 p-5"><h2 className="font-black">关联录音</h2><p className="mt-1 text-xs text-slate-500">选择录音并查看转写证据</p></div>{recordings.map((recording) => <button key={recording.id} onClick={() => { setActiveRecording(recording); setCurrentTime(0); }} className={`flex w-full items-center gap-3 border-b border-slate-100 px-5 py-4 text-left last:border-0 ${activeRecording.id === recording.id ? "bg-[#eaf5f1]" : "hover:bg-slate-50"}`}><span className={`flex h-9 w-9 items-center justify-center rounded-full ${activeRecording.id === recording.id ? "bg-[#0d5b4f] text-white" : "bg-slate-100"}`}>▶</span><span className="min-w-0"><strong className="block truncate text-sm">{recording.name}</strong><span className="text-xs text-slate-400">{recording.id} · {formatTime(recording.duration)}</span></span></button>)}</section>
          <section className="rounded-2xl bg-[#102c28] p-5 text-white shadow-lg"><p className="truncate text-sm font-black">{activeRecording.name}</p><audio ref={audioRef} src={activeRecording.url} controls className="mt-4 w-full" onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}>浏览器不支持音频播放</audio><p className="mt-2 text-right font-mono text-xs text-emerald-200">当前位置 {formatTime(currentTime)}</p></section>
          <section className="rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-100 p-5"><h2 className="font-black">转写文本</h2><p className="mt-1 text-xs text-slate-500">浅绿色段落为 AI 证据</p></div><div className="max-h-[480px] space-y-1 overflow-y-auto p-3">{activeTranscript.map((line) => <button key={`${line.recordingId}-${line.time}`} onClick={() => seek(line.recordingId, line.time)} className={`w-full rounded-xl p-3 text-left ${line.evidence ? "bg-emerald-50 ring-1 ring-emerald-100" : "hover:bg-slate-50"}`}><div className="flex items-center gap-2"><span className="font-mono text-xs font-black text-[#137161]">{formatTime(line.time)}</span><span className="text-xs text-slate-400">{line.speaker}</span>{line.evidence && <span className="ml-auto rounded bg-white px-2 py-0.5 text-[10px] font-bold text-emerald-700">AI 证据</span>}</div><p className="mt-1 text-sm leading-6 text-slate-700">{line.text}</p></button>)}</div></section>
        </aside>

        <section className="min-w-0 space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between"><div><h2 className="text-xl font-black">字段审核表</h2><p className="mt-1 text-sm text-slate-500">逐项核对原始填报与录音证据，确认最终值。</p></div><div className="flex items-center gap-3"><span className="text-sm font-bold">已确认 {confirmedCount}/{fields.length}</span><button onClick={confirmMatched} className="rounded-xl bg-emerald-50 px-4 py-2 text-sm font-black text-emerald-700">一键确认无误字段</button></div></div><div className="mt-4 h-2 rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#137161] transition-all" style={{ width: `${confirmedCount / fields.length * 100}%` }}/></div><div className="mt-4 flex flex-wrap gap-2">{(["matched", "pending", "conflict", "missing"] as const).map((status) => <span key={status} className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${fieldStatusMeta[status].className}`}><span className={`h-2 w-2 rounded-full ${fieldStatusMeta[status].dot}`}/>{fieldStatusMeta[status].label}</span>)}</div></div>

          <div className="hidden overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm lg:block"><table className="w-full min-w-[1050px] text-left"><thead className="bg-slate-50 text-xs text-slate-500"><tr>{["字段名称", "Excel 填报值", "AI 录音值", "置信度", "状态", "人工最终值", "修改原因", "录音证据", "确认"].map((label) => <th key={label} className="px-3 py-3 font-black">{label}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{fields.map((field) => <tr key={field.key} className={field.confirmed ? "bg-emerald-50/30" : ""}><td className="px-3 py-4 text-sm font-black">{field.label}</td><td className="px-3 py-4 text-sm">{field.excel} {field.unit}</td><td className="px-3 py-4 text-sm font-bold text-[#0d5b4f]">{field.ai} {field.unit}</td><td className="px-3 py-4 text-sm font-black tabular-nums">{Math.round(field.confidence * 100)}%</td><td className="px-3 py-4"><span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-bold ${fieldStatusMeta[field.status].className}`}><span className={`h-2 w-2 rounded-full ${fieldStatusMeta[field.status].dot}`}/>{fieldStatusMeta[field.status].label}</span></td><td className="px-3 py-4"><input aria-label={`${field.label}人工最终值`} value={field.final} onChange={(event) => updateField(field.key, { final: event.target.value, confirmed: false })} className="w-28 rounded-lg border border-slate-300 px-2 py-2 text-sm outline-none focus:border-[#137161]"/></td><td className="px-3 py-4"><input aria-label={`${field.label}修改原因`} value={field.reason} onChange={(event) => updateField(field.key, { reason: event.target.value, confirmed: false })} placeholder="修改时必填" className="w-36 rounded-lg border border-slate-300 px-2 py-2 text-sm outline-none focus:border-[#137161]"/></td><td className="px-3 py-4">{field.evidence ? <button onClick={() => seek(field.evidence!.recordingId, field.evidence!.start)} className="whitespace-nowrap rounded-lg bg-slate-900 px-2.5 py-2 font-mono text-xs font-bold text-white">▶ {formatTime(field.evidence.start)}</button> : <span className="text-slate-400">—</span>}</td><td className="px-3 py-4"><button onClick={() => confirmField(field)} className={`rounded-lg px-3 py-2 text-xs font-black ${field.confirmed ? "bg-emerald-100 text-emerald-700" : "bg-[#0d5b4f] text-white"}`}>{field.confirmed ? "✓ 已确认" : "确认"}</button></td></tr>)}</tbody></table></div>

          <div className="space-y-3 lg:hidden">{fields.map((field) => <article key={field.key} className={`rounded-2xl border bg-white p-5 shadow-sm ${field.confirmed ? "border-emerald-300" : "border-slate-200"}`}><div className="flex items-start justify-between gap-3"><div><h3 className="font-black">{field.label}</h3><p className="mt-1 text-xs text-slate-400">AI 置信度 {Math.round(field.confidence * 100)}%</p></div><span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold ${fieldStatusMeta[field.status].className}`}><span className={`h-2 w-2 rounded-full ${fieldStatusMeta[field.status].dot}`}/>{fieldStatusMeta[field.status].label}</span></div><div className="mt-4 grid grid-cols-2 gap-3"><div className="rounded-xl bg-slate-50 p-3"><p className="text-xs text-slate-400">Excel 值</p><p className="mt-1 font-bold">{field.excel} {field.unit}</p></div><div className="rounded-xl bg-emerald-50 p-3"><p className="text-xs text-emerald-600">AI 录音值</p><p className="mt-1 font-bold text-emerald-900">{field.ai} {field.unit}</p></div></div>{field.evidence && <button onClick={() => seek(field.evidence!.recordingId, field.evidence!.start)} className="mt-3 w-full rounded-xl border border-slate-200 p-3 text-left text-sm"><span className="font-mono text-xs font-black text-[#137161]">▶ {formatTime(field.evidence.start)}–{formatTime(field.evidence.end)}</span><p className="mt-1 text-slate-600">“{field.evidence.text}”</p></button>}<div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="text-xs font-bold text-slate-500">人工最终值<input value={field.final} onChange={(event) => updateField(field.key, { final: event.target.value, confirmed: false })} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none"/></label><label className="text-xs font-bold text-slate-500">修改原因<input value={field.reason} onChange={(event) => updateField(field.key, { reason: event.target.value, confirmed: false })} placeholder="修改时必填" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none"/></label></div><button onClick={() => confirmField(field)} className={`mt-4 w-full rounded-xl py-2.5 text-sm font-black ${field.confirmed ? "bg-emerald-100 text-emerald-700" : "bg-[#0d5b4f] text-white"}`}>{field.confirmed ? "✓ 此字段已确认" : "确认此字段"}</button></article>)}</div>

          <div className="sticky bottom-3 flex flex-col gap-4 rounded-2xl bg-[#102c28] p-5 text-white shadow-xl sm:flex-row sm:items-center sm:justify-between"><div><p className="font-black">审核进度 {confirmedCount}/{fields.length}</p><p className="mt-1 text-xs text-slate-300">修改原值时必须填写修改原因</p></div><div className="flex gap-2"><button onClick={saveDraft} className="flex-1 rounded-xl border border-white/30 px-4 py-3 text-sm font-bold sm:flex-none">保存草稿</button><button onClick={submitReview} className="flex-1 rounded-xl bg-emerald-400 px-5 py-3 text-sm font-black text-[#102c28] sm:flex-none">提交完成审核</button></div></div>
        </section>
      </div>
    </main>
  </div>;
}
