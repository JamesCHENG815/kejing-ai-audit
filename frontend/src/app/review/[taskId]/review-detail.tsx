"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL, apiRequest, downloadFile, withToken } from "@/lib/api";
import { formatBeijingDateTime } from "@/lib/date-time";
import {
  buildReviewModules,
  fieldStatusMeta,
  ReviewField,
  ReviewTask,
  taskStatusMeta,
} from "@/lib/review-data";

type Recording = { id: string; name: string; duration: number; url?: string };
type Transcript = { recordingId: string; time: number; speaker: string; text: string; evidence?: boolean };
type History = {
  who: string;
  when: string;
  action: string;
  kind?: "change" | "reason" | "save" | "submit" | "legacy" | "ai" | "event";
  field?: string | null;
  before?: string | null;
  after?: string | null;
  reason?: string | null;
};
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

const HISTORY_DOT: Record<string, string> = {
  change: "bg-amber-500",
  reason: "bg-amber-400",
  save: "bg-[#137161]",
  submit: "bg-emerald-600",
  legacy: "bg-slate-400",
  ai: "bg-blue-500",
  event: "bg-[#137161]",
};

function HistoryItem({ item }: { item: History }) {
  return (
    <div className="flex gap-3 text-sm">
      <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${HISTORY_DOT[item.kind ?? "event"] ?? "bg-[#137161]"}`} />
      <div className="min-w-0">
        <p><strong>{item.who}</strong> · {item.action}</p>
        {item.kind === "change" && (
          <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
            <span className="rounded bg-rose-50 px-1.5 py-0.5 font-mono text-rose-700 ring-1 ring-rose-100">{item.before || "—"}</span>
            <span className="text-slate-400">→</span>
            <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-mono text-emerald-700 ring-1 ring-emerald-100">{item.after || "—"}</span>
          </p>
        )}
        {item.reason && <p className="mt-1 text-xs text-slate-500">原因：{item.reason}</p>}
        <p className="mt-0.5 text-xs text-slate-400">{formatBeijingDateTime(item.when)}（北京时间）</p>
      </div>
    </div>
  );
}

export default function ReviewDetail({ taskId }: { taskId: string }) {
  const [task, setTask] = useState<ReviewTask | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const evidenceEndRef = useRef<number | null>(null);
  const submitNoticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [activeRecording, setActiveRecording] = useState<Recording | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [fields, setFields] = useState<ReviewField[]>([]);
  const [history, setHistory] = useState<History[]>([]);
  const [hasAiAnalysis, setHasAiAnalysis] = useState(false);
  const [hasTranscript, setHasTranscript] = useState(false);
  const [busy, setBusy] = useState<"analyze" | "draft" | "submit" | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [showSubmitNotice, setShowSubmitNotice] = useState(false);

  const applyDetail = useCallback(
    (data: ReviewDetailResponse, options?: { keepPlayback?: boolean }) => {
      const resolvedRecordings = data.recordings.map((item) => ({
        ...item,
        // <audio> 发不出自定义请求头，令牌只能跟在查询串上。
        url: item.url ? withToken(`${API_BASE_URL}${item.url}`) : undefined,
      }));
      setTask(data.task);
      setFields(data.fields);
      setRecordings(resolvedRecordings);
      // 保存草稿后刷新时不要把正在播放的录音切回第一条，否则经理要重新定位。
      setActiveRecording((previous) =>
        options?.keepPlayback && previous
          ? resolvedRecordings.find((item) => item.id === previous.id) ?? resolvedRecordings[0] ?? null
          : resolvedRecordings[0] ?? null,
      );
      setTranscripts(data.transcripts);
      setHistory(data.history);
      setHasAiAnalysis(data.hasAiAnalysis);
      setHasTranscript(data.hasTranscript);
    },
    [],
  );

  const refreshHistory = useCallback(async () => {
    try {
      const data = await apiRequest<ReviewDetailResponse>(`/api/review-tasks/${taskId}`);
      applyDetail(data, { keepPlayback: true });
    } catch {
      // 历史刷新失败不影响已经保存成功的审核结果。
    }
  }, [applyDetail, taskId]);

  useEffect(() => () => {
    if (submitNoticeTimerRef.current) clearTimeout(submitNoticeTimerRef.current);
  }, []);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function loadDetail() {
      try {
        const data = await apiRequest<ReviewDetailResponse>(`/api/review-tasks/${taskId}`);
        if (!active) return;
        applyDetail(data);
        if (data.task.status === "analyzing") {
          timer = setTimeout(loadDetail, 3000);
        }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "审核任务加载失败");
      }
    }
    loadDetail();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [applyDetail, taskId]);

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

  async function exportCurrent() {
    setError("");
    try {
      await downloadFile(
        `/api/review-tasks/${taskId}/export`,
        `${task?.store ?? "门店"}_审核结果.csv`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导出失败");
    }
  }

  async function retryAnalysis() {
    const confirmed = window.confirm(
      "重新分析会重新转写录音、刷新 AI 字段结果，并产生 OpenAI API 费用。当前未保存的审核修改将丢失，是否继续？",
    );
    if (!confirmed) return;
    setBusy("analyze");
    setError("");
    setMessage("");
    setTask((current) => current ? { ...current, status: "analyzing" } : current);
    try {
      await apiRequest(`/api/review-tasks/${taskId}/analyze`, {
        method: "POST",
        body: JSON.stringify({ force: true }),
      });
      const data = await apiRequest<ReviewDetailResponse>(`/api/review-tasks/${taskId}`);
      applyDetail(data, { keepPlayback: true });
      setMessage("AI 重新分析完成，录音转写和字段结果已刷新。");
    } catch (reason) {
      setTask((current) => current ? { ...current, status: "analysis_failed" } : current);
      setError(reason instanceof Error ? reason.message : "AI 重新分析失败");
    } finally {
      setBusy(null);
    }
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
    setMessage("审核草稿已保存。");
    // 历史由后端事件表返回，不再在前端凭本地状态拼一条假记录。
    await refreshHistory();
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
    setMessage("审核已提交完成。");
    await refreshHistory();
    setShowSubmitNotice(true);
    if (submitNoticeTimerRef.current) clearTimeout(submitNoticeTimerRef.current);
    submitNoticeTimerRef.current = setTimeout(() => setShowSubmitNotice(false), 3000);
    setBusy(null);
  }

  if (!task) {
    return <div className="min-h-screen bg-[#f3f6f5] p-10 text-center text-slate-500">{error || "正在加载真实审核数据…"}</div>;
  }

  return <div className="min-h-screen bg-[#f3f6f5] text-slate-950">
    {showSubmitNotice && <div role="status" aria-live="polite" className="fixed left-1/2 top-5 z-50 flex -translate-x-1/2 items-center gap-3 rounded-2xl border border-emerald-100 bg-white px-4 py-3 text-left shadow-[0_16px_40px_rgba(15,61,53,0.18)]"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-lg font-black text-emerald-700">✓</span><span><strong className="block text-sm font-black text-slate-900">提交成功</strong><span className="mt-0.5 block text-xs text-slate-500">审核结果已保存</span></span></div>}
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
          <button onClick={exportCurrent} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold">导出当前门店</button>
          <button onClick={() => setShowHistory((value) => !value)} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold">审核历史 {showHistory ? "↑" : "↓"}</button>
          <button onClick={retryAnalysis} disabled={busy !== null || !recordings.length || task.status === "analyzing" || task.status === "reviewing" || task.status === "completed"} className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm font-bold text-blue-700 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50">{busy === "analyze" ? "AI 分析中…" : "↻ 重新进行 AI 分析"}</button>
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
      {!hasAiAnalysis && <div className={`mb-5 flex flex-col gap-3 rounded-xl border px-4 py-4 text-sm font-bold sm:flex-row sm:items-center sm:justify-between ${task.status === "analysis_failed" ? "border-rose-200 bg-rose-50 text-rose-800" : task.status === "analyzing" ? "border-blue-200 bg-blue-50 text-blue-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}><span>{task.status === "analysis_failed" ? "AI 分析失败，请检查 OpenAI 配置或网络后重试。" : task.status === "analyzing" ? "AI 正在后台转写录音并提取字段，请稍候。" : "暂无 AI 分析结果。当前仅展示 Excel 填报值，请先完成录音转写与 AI 字段提取。"}</span>{task.status === "analysis_failed" && <button onClick={retryAnalysis} disabled={busy !== null} className="shrink-0 rounded-lg bg-rose-700 px-4 py-2 text-xs font-black text-white hover:bg-rose-800 disabled:cursor-not-allowed disabled:opacity-60">重新分析</button>}{task.status === "analyzing" && busy === "analyze" && <span className="shrink-0 text-xs">重新分析中…</span>}</div>}
      {showHistory && <section className="mb-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><h2 className="font-black">审核历史</h2><p className="mt-1 text-xs text-slate-500">按时间倒序，来自后端事件表；升级前的记录标注为“升级前保存”。</p><div className="mt-4 space-y-3">{history.length ? history.map((item, index) => <HistoryItem key={`${item.when}-${index}`} item={item} />) : <p className="text-sm text-slate-400">暂无审核历史</p>}</div></section>}

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
                <td className="px-2 py-3 text-xs font-bold text-[#0d5b4f]">{!hasAiAnalysis ? <span className="font-medium text-slate-400">暂无 AI 分析结果</span> : <div className="space-y-2">{group.map((field) => <p key={field.key} className={`min-h-5 break-words ${field.status === "missing" ? "text-slate-500" : ""}`}>{field.status === "missing" ? "数据缺失" : <>{field.ai} {field.unit}</>}</p>)}</div>}</td>
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
