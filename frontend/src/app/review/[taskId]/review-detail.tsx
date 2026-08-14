"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL, apiRequest } from "@/lib/api";
import {
  buildReviewModules,
  fieldStatusMeta,
  ReviewField,
  ReviewTask,
  taskStatusMeta,
} from "@/lib/review-data";

type Recording = { id: string; name: string; duration: number; url?: string };
type Transcript = { recordingId: string; time: number; speaker: string; text: string; evidence?: boolean };
type History = { who: string; when: string; action: string };
type ReviewDetailResponse = {
  task: ReviewTask;
  fields: ReviewField[];
  recordings: Recording[];
  transcripts: Transcript[];
  history: History[];
  hasAiAnalysis: boolean;
  hasTranscript: boolean;
};

const PRODUCT_PART_LABELS: Record<string, string> = {
  name: "单品名称",
  bottles: "上月零售瓶数",
  price: "单品进货价格",
};

function formatTime(value: number) {
  return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, "0")}`;
}

function formatPreciseTime(value: number) {
  const minutes = Math.floor(value / 60);
  const seconds = (value % 60).toFixed(1).padStart(4, "0");
  return `${minutes}:${seconds}`;
}

function shortLabel(field: ReviewField) {
  const brand = ["马爹利", "轩尼诗", "人头马", "白酒", "威士忌"].find((item) => field.key.includes(item));
  return brand ?? field.label;
}

function productPart(field: ReviewField) {
  if (field.key.endsWith("产品瓶数")) return PRODUCT_PART_LABELS.bottles;
  if (field.key.endsWith("进货价")) return PRODUCT_PART_LABELS.price;
  return PRODUCT_PART_LABELS.name;
}

function groupStatus(group: ReviewField[]) {
  if (group.some((field) => field.status === "conflict")) return "conflict" as const;
  if (group.some((field) => field.status === "pending")) return "pending" as const;
  if (group.every((field) => field.status === "missing")) return "missing" as const;
  if (group.some((field) => field.status === "missing")) return "pending" as const;
  return "matched" as const;
}

export default function ReviewDetail({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<ReviewTask | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const evidenceEndRef = useRef<number | null>(null);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [activeRecording, setActiveRecording] = useState<Recording | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [fields, setFields] = useState<ReviewField[]>([]);
  const [history, setHistory] = useState<History[]>([]);
  const [hasAiAnalysis, setHasAiAnalysis] = useState(false);
  const [hasTranscript, setHasTranscript] = useState(false);
  const [busy, setBusy] = useState<"draft" | "submit" | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    let active = true;
    apiRequest<ReviewDetailResponse>(`/api/review-tasks/${taskId}`)
      .then((data) => {
        if (!active) return;
        const resolvedRecordings = data.recordings.map((item) => ({
          ...item,
          url: item.url ? `${API_BASE_URL}${item.url}` : undefined,
        }));
        setTask(data.task);
        setFields(data.fields);
        setRecordings(resolvedRecordings);
        setActiveRecording(resolvedRecordings[0] ?? null);
        setTranscripts(data.transcripts);
        setHistory(data.history);
        setHasAiAnalysis(data.hasAiAnalysis);
        setHasTranscript(data.hasTranscript);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "审核任务加载失败");
      });
    return () => { active = false; };
  }, [taskId]);

  const modules = useMemo(() => buildReviewModules(fields), [fields]);
  const confirmedCount = fields.filter((field) => field.confirmed).length;
  const activeTranscript = transcripts.filter((line) => line.recordingId === activeRecording?.id);

  function seek(recordingId: string, time: number, endTime?: number) {
    const recording = recordings.find((item) => item.id === recordingId) ?? activeRecording;
    if (!recording) return;
    evidenceEndRef.current = endTime ?? null;
    setActiveRecording(recording);
    setCurrentTime(time);
    window.setTimeout(() => {
      if (!audioRef.current) return;
      audioRef.current.currentTime = time;
      audioRef.current.play().catch(() => undefined);
    }, 0);
  }

  function updateField(key: string, patch: Partial<ReviewField>) {
    setFields((current) => current.map((field) => field.key === key ? { ...field, ...patch } : field));
    setMessage("");
  }

  function toggleGroupConfirmation(group: ReviewField[]) {
    const keys = new Set(group.map((field) => field.key));
    if (group.every((field) => field.confirmed)) {
      setFields((current) => current.map((field) => keys.has(field.key) ? { ...field, confirmed: false } : field));
      setError("");
      setMessage("已取消确认，可以继续修改。");
      return;
    }
    const invalid = group.find((field) => field.final !== field.excel && !field.reason.trim());
    if (invalid) return setError(`“${invalid.label}”修改了原值，请填写修改原因`);
    setFields((current) => current.map((field) => keys.has(field.key) ? { ...field, confirmed: true } : field));
    setError("");
    setMessage("字段已确认。如需修改，请先点击“取消”。");
  }

  function confirmMatched() {
    setFields((current) => current.map((field) => field.status === "matched" ? { ...field, confirmed: true, final: field.excel } : field));
    setMessage("一致字段已全部确认。");
  }

  async function saveDraft() {
    setBusy("draft");
    setError("");
    try {
      await apiRequest(`/api/review-tasks/${taskId}/draft`, {
        method: "PUT",
        body: JSON.stringify({ fields }),
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "草稿保存失败");
      setBusy(null);
      return;
    }
    setHistory((current) => [{
      who: "当前经理",
      when: new Date().toLocaleString("zh-CN", { hour12: false }),
      action: `保存审核草稿，已确认 ${confirmedCount}/${fields.length} 个字段`,
    }, ...current]);
    setMessage("审核草稿已保存。");
    setBusy(null);
  }

  async function submitReview() {
    if (confirmedCount !== fields.length) return setError(`还有 ${fields.length - confirmedCount} 个字段未确认`);
    const invalid = fields.find((field) => field.final !== field.excel && !field.reason.trim());
    if (invalid) return setError(`“${invalid.label}”需要填写修改原因`);
    setBusy("submit");
    setError("");
    try {
      await apiRequest(`/api/review-tasks/${taskId}/submit`, {
        method: "POST",
        body: JSON.stringify({ fields }),
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "审核提交失败");
      setBusy(null);
      return;
    }
    setTask((current) => current ? { ...current, status: "completed" } : current);
    setHistory((current) => [{ who: "当前经理", when: new Date().toLocaleString("zh-CN", { hour12: false }), action: "提交并完成审核" }, ...current]);
    setMessage("审核已提交完成。");
    setBusy(null);
  }

  if (!task) {
    return <div className="min-h-screen bg-[#f3f6f5] p-10 text-center text-slate-500">{error || "正在加载真实审核数据…"}</div>;
  }

  return <div className="min-h-screen bg-[#f3f6f5] text-slate-950">
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-[1800px] flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <Link href="/review" className="text-sm font-bold text-[#137161]">← 返回审核任务</Link>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-black">{task.store}</h1>
            <span className={`rounded-full px-3 py-1 text-xs font-black ring-1 ${taskStatusMeta[task.status].className}`}>{taskStatusMeta[task.status].label}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <a href={`${API_BASE_URL}/api/review-tasks/export`} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold">导出结果</a>
          <button onClick={() => setShowHistory((value) => !value)} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold">审核历史 {showHistory ? "↑" : "↓"}</button>
          <button onClick={saveDraft} disabled={busy !== null} className="rounded-xl border border-[#0d5b4f] px-4 py-2.5 text-sm font-bold text-[#0d5b4f]">{busy === "draft" ? "保存中…" : "保存草稿"}</button>
          <button onClick={submitReview} disabled={busy !== null} className="rounded-xl bg-[#0d5b4f] px-5 py-2.5 text-sm font-black text-white">{busy === "submit" ? "提交中…" : "提交完成审核"}</button>
        </div>
      </div>
    </header>

    <main className="mx-auto max-w-[1800px] px-4 py-6 sm:px-6">
      <section className="mb-5 grid gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:grid-cols-2 xl:grid-cols-5">
        {[
          ["门店 ID", task.customerId],
          ["门店名称", task.store],
          ["地址", task.address || "—"],
          ["拜访人", task.visitor],
          ["拜访日期", task.visitDate || "—"],
        ].map(([label, value]) => <div key={label} className="min-w-0"><p className="text-xs font-bold text-slate-400">{label}</p><p className="mt-1 break-words text-sm font-black text-slate-800">{value}</p></div>)}
      </section>

      {(error || message) && <div className={`mb-5 flex justify-between rounded-xl border px-4 py-3 text-sm font-bold ${error ? "border-rose-200 bg-rose-50 text-rose-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}><span>{error || message}</span><button onClick={() => { setError(""); setMessage(""); }}>×</button></div>}
      {!hasAiAnalysis && <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm font-bold text-amber-800">暂无 AI 分析结果。当前仅展示 Excel 填报值，请先完成录音转写与 AI 字段提取。</div>}
      {showHistory && <section className="mb-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><h2 className="font-black">审核历史</h2><div className="mt-4 space-y-3">{history.length ? history.map((item, index) => <div key={`${item.when}-${index}`} className="flex gap-3 text-sm"><span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-[#137161]"/><div><p><strong>{item.who}</strong> · {item.action}</p><p className="mt-0.5 text-xs text-slate-400">{item.when}</p></div></div>) : <p className="text-sm text-slate-400">暂无审核历史</p>}</div></section>}

      <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)] 2xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 p-5"><h2 className="font-black">关联录音</h2><p className="mt-1 text-xs text-slate-500">选择录音并查看转写证据</p></div>
            {recordings.length === 0 ? <p className="p-5 text-sm text-slate-400">此任务没有关联录音</p> : recordings.map((recording) => <button key={recording.id} onClick={() => { evidenceEndRef.current = null; setActiveRecording(recording); setCurrentTime(0); }} className={`flex w-full items-center gap-3 border-b border-slate-100 px-5 py-4 text-left last:border-0 ${activeRecording?.id === recording.id ? "bg-[#eaf5f1]" : "hover:bg-slate-50"}`}><span className={`flex h-9 w-9 items-center justify-center rounded-full ${activeRecording?.id === recording.id ? "bg-[#0d5b4f] text-white" : "bg-slate-100"}`}>▶</span><span className="min-w-0"><strong className="block truncate text-sm">{recording.name}</strong><span className="text-xs text-slate-400">{recording.id} · {formatTime(recording.duration)}</span></span></button>)}
          </section>
          {activeRecording && <section className="rounded-2xl bg-[#102c28] p-5 text-white shadow-lg"><p className="truncate text-sm font-black">{activeRecording.name}</p><audio ref={audioRef} src={activeRecording.url} controls className="mt-4 w-full" onTimeUpdate={(event) => { const time = event.currentTarget.currentTime; setCurrentTime(time); if (evidenceEndRef.current !== null && time >= evidenceEndRef.current) { event.currentTarget.pause(); evidenceEndRef.current = null; } }}>浏览器不支持音频播放</audio><p className="mt-2 text-right font-mono text-xs text-emerald-200">当前位置 {formatPreciseTime(currentTime)}</p></section>}
          <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 p-5"><h2 className="font-black">转写文本</h2><p className="mt-1 text-xs text-slate-500">浅绿色段落为 AI 证据</p></div>
            {!hasTranscript ? <p className="p-5 text-sm font-bold text-slate-400">暂无 AI 分析结果：尚无录音转写</p> : <div className="max-h-[480px] space-y-1 overflow-y-auto p-3">{activeTranscript.length ? activeTranscript.map((line) => <button key={`${line.recordingId}-${line.time}`} onClick={() => seek(line.recordingId, line.time)} className={`w-full rounded-xl p-3 text-left ${line.evidence ? "bg-emerald-50 ring-1 ring-emerald-100" : "hover:bg-slate-50"}`}><div className="flex items-center gap-2"><span className="font-mono text-xs font-black text-[#137161]">{formatTime(line.time)}</span><span className="text-xs text-slate-400">{line.speaker}</span>{line.evidence && <span className="ml-auto rounded bg-white px-2 py-0.5 text-[10px] font-bold text-emerald-700">AI 证据</span>}</div><p className="mt-1 text-sm leading-6 text-slate-700">{line.text}</p></button>) : <p className="p-2 text-sm text-slate-400">当前录音暂无转写文本</p>}</div>}
          </section>
        </aside>

        <section className="min-w-0 space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between"><div><h2 className="text-xl font-black">字段审核</h2><p className="mt-1 text-sm text-slate-500">按四个业务模块核对 Excel、录音证据与最终值。</p></div><div className="flex items-center gap-3"><span className="text-sm font-bold">已确认 {confirmedCount}/{fields.length}</span><button onClick={confirmMatched} className="rounded-xl bg-emerald-50 px-4 py-2 text-sm font-black text-emerald-700">一键确认无误字段</button></div></div>
            <div className="mt-4 h-2 rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#137161] transition-all" style={{ width: `${fields.length ? confirmedCount / fields.length * 100 : 0}%` }}/></div>
          </div>

          {modules.map((module) => <section key={module.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 bg-slate-50 px-5 py-4"><h3 className="text-lg font-black text-[#0d5b4f]">{module.title}</h3><p className="mt-1 text-xs text-slate-500">{module.description}</p></div>
            {module.groups.length === 0 ? <p className="px-5 py-8 text-center text-sm text-slate-400">当前任务没有该模块字段</p> : <div className="overflow-x-auto"><table className="w-full min-w-[1120px] table-fixed text-left"><colgroup><col className="w-[15%]"/><col className="w-[14%]"/><col className="w-[12%]"/><col className="w-[7%]"/><col className="w-[8%]"/><col className="w-[12%]"/><col className="w-[13%]"/><col className="w-[13%]"/><col className="w-[6%]"/></colgroup><thead className="bg-white text-[11px] text-slate-500"><tr>{["字段名称", "Excel 填报值", "AI 录音值", "置信度", "状态", "人工最终值", "修改原因", "录音证据", "确认"].map((label) => <th key={label} className="px-2 py-3 font-black">{label}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{module.groups.map((group, groupIndex) => {
              const status = groupStatus(group);
              const isProduct = module.id === "products";
              const confirmed = group.every((field) => field.confirmed);
              return <tr key={group.map((field) => field.key).join("|")} className={confirmed ? "bg-emerald-50/30" : ""}>
                <td className="px-2 py-3 text-xs font-black">{isProduct ? `畅销产品 ${groupIndex + 1}` : shortLabel(group[0])}{isProduct && <div className="mt-2 space-y-2 text-[10px] font-medium text-slate-400">{group.map((field) => <p key={field.key}>{productPart(field)}</p>)}</div>}</td>
                <td className="px-2 py-3 text-xs"><div className="space-y-2">{group.map((field) => <p key={field.key} className="min-h-5 break-words">{field.excel} {field.unit}</p>)}</div></td>
                <td className="px-2 py-3 text-xs font-bold text-[#0d5b4f]">{!hasAiAnalysis ? <span className="font-medium text-slate-400">暂无 AI 分析结果</span> : <div className="space-y-2">{group.map((field) => <p key={field.key} className="min-h-5 break-words">{field.ai} {field.unit}</p>)}</div>}</td>
                <td className="px-2 py-3 text-xs font-black">{!hasAiAnalysis ? "—" : <div className="space-y-2">{group.map((field) => <p key={field.key} className="min-h-5">{Math.round(field.confidence * 100)}%</p>)}</div>}</td>
                <td className="px-2 py-3"><span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-1 text-[10px] font-bold ${fieldStatusMeta[status].className}`}><span className={`h-1.5 w-1.5 rounded-full ${fieldStatusMeta[status].dot}`}/>{fieldStatusMeta[status].label}</span></td>
                <td className="px-2 py-3"><div className="space-y-2">{group.map((field) => <input key={field.key} aria-label={`${field.label}人工最终值`} value={field.final} disabled={confirmed} onChange={(event) => updateField(field.key, { final: event.target.value, confirmed: false })} className="block h-8 w-full min-w-0 rounded-lg border border-slate-300 px-2 text-xs outline-none focus:border-[#137161] disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-500"/>)}</div></td>
                <td className="px-2 py-3"><div className="space-y-2">{group.map((field) => <input key={field.key} aria-label={`${field.label}修改原因`} value={field.reason} disabled={confirmed} onChange={(event) => updateField(field.key, { reason: event.target.value, confirmed: false })} placeholder="修改时必填" className="block h-8 w-full min-w-0 rounded-lg border border-slate-300 px-2 text-xs outline-none focus:border-[#137161] disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-500"/>)}</div></td>
                <td className="px-2 py-3"><div className="space-y-2">{group.map((field) => field.evidence ? <button key={field.key} title={field.evidence.text} onClick={() => seek(field.evidence!.recordingId, field.evidence!.start, field.evidence!.end)} className="block h-8 w-full whitespace-nowrap rounded-lg bg-slate-900 px-2 text-center font-mono text-[10px] font-bold text-white">▶ {formatPreciseTime(field.evidence.start)}–{formatPreciseTime(field.evidence.end)}</button> : <span key={field.key} className="block h-8 pt-2 text-slate-400">—</span>)}</div></td>
                <td className="px-2 py-3"><button onClick={() => toggleGroupConfirmation(group)} className={`w-full whitespace-nowrap rounded-lg px-2 py-2 text-[10px] font-black ${confirmed ? "bg-rose-50 text-rose-700 ring-1 ring-rose-200" : "bg-[#0d5b4f] text-white"}`}>{confirmed ? "取消" : "确认"}</button></td>
              </tr>;
            })}</tbody></table></div>}
          </section>)}

          <div className="sticky bottom-3 flex flex-col gap-4 rounded-2xl bg-[#102c28] p-5 text-white shadow-xl sm:flex-row sm:items-center sm:justify-between"><div><p className="font-black">审核进度 {confirmedCount}/{fields.length}</p><p className="mt-1 text-xs text-slate-300">修改原值时必须填写修改原因</p></div><div className="flex gap-2"><button onClick={saveDraft} className="flex-1 rounded-xl border border-white/30 px-4 py-3 text-sm font-bold sm:flex-none">保存草稿</button><button onClick={submitReview} className="flex-1 rounded-xl bg-emerald-400 px-5 py-3 text-sm font-black text-[#102c28] sm:flex-none">提交完成审核</button></div></div>
        </section>
      </div>
    </main>
  </div>;
}
