"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

type Status = "matched" | "conflict" | "missing" | "reviewed";

type AuditField = {
  key: string;
  label: string;
  excelValue: string;
  aiValue: string;
  unit?: string;
  confidence: number;
  status: Status;
  evidence?: { recording: string; start: number; end: number; text: string };
  finalValue: string;
  changeReason: string;
};

const recordings = [
  { id: "REC-001", name: "风筝酒业.m4a", duration: 184 },
  { id: "REC-002", name: "风筝酒业(1).m4a", duration: 152 },
];

const transcript = [
  { time: 8, speaker: "业务员", text: "老板您好，今天想了解一下门店今年的销售情况。" },
  { time: 34, speaker: "门店", text: "今年到三月底大概卖了八万左右，比去年同期稍好一点。" },
  { time: 78, speaker: "业务员", text: "马爹利这边去年全年大概是多少？畅销的是哪些产品？" },
  { time: 125.2, speaker: "门店", text: "马爹利去年大概二十万，蓝带和名士卖得比较好。" },
  { time: 143, speaker: "业务员", text: "现在经营上还有什么问题吗？" },
  { time: 151, speaker: "门店", text: "主要是客流少了一些，希望活动支持能多一点。" },
];

const initialFields: AuditField[] = [
  { key: "lastYearSales", label: "去年销售额", excelValue: "25", aiValue: "20", unit: "万元", confidence: 0.95, status: "conflict", evidence: { recording: "REC-001", start: 125.2, end: 131.6, text: "马爹利去年大概二十万" }, finalValue: "20", changeReason: "" },
  { key: "salesToMarch", label: "今年截至三月销售额", excelValue: "8", aiValue: "8", unit: "万元", confidence: 0.92, status: "matched", evidence: { recording: "REC-001", start: 34, end: 41.5, text: "今年到三月底大概卖了八万左右" }, finalValue: "8", changeReason: "" },
  { key: "bestSellers", label: "畅销产品", excelValue: "蓝带、名士", aiValue: "蓝带、名士", confidence: 0.91, status: "matched", evidence: { recording: "REC-001", start: 130, end: 136, text: "蓝带和名士卖得比较好" }, finalValue: "蓝带、名士", changeReason: "" },
  { key: "otherIssues", label: "其他问题", excelValue: "—", aiValue: "客流减少，希望增加活动支持", confidence: 0.84, status: "missing", evidence: { recording: "REC-001", start: 151, end: 160, text: "主要是客流少了一些，希望活动支持能多一点" }, finalValue: "客流减少，希望增加活动支持", changeReason: "" },
];

const statusStyle: Record<Status, { label: string; className: string; border: string }> = {
  matched: { label: "一致", className: "bg-emerald-100 text-emerald-700", border: "border-l-emerald-500" },
  conflict: { label: "冲突", className: "bg-rose-100 text-rose-700", border: "border-l-rose-500" },
  missing: { label: "Excel 缺失", className: "bg-amber-100 text-amber-700", border: "border-l-amber-500" },
  reviewed: { label: "已人工确认", className: "bg-blue-100 text-blue-700", border: "border-l-blue-500" },
};

function formatTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

export default function ReviewDetail({ taskId }: { taskId: string }) {
  const [activeRecording, setActiveRecording] = useState(recordings[0]);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [fields, setFields] = useState(initialFields);
  const [saved, setSaved] = useState(false);

  const progress = useMemo(() => (currentTime / activeRecording.duration) * 100, [activeRecording, currentTime]);

  function seek(time: number, recordingId?: string) {
    const recording = recordings.find((item) => item.id === recordingId) ?? activeRecording;
    setActiveRecording(recording);
    setCurrentTime(Math.min(time, recording.duration));
    setIsPlaying(true);
  }

  function updateField(key: string, update: Partial<AuditField>) {
    setFields((current) => current.map((field) => field.key === key ? { ...field, ...update } : field));
    setSaved(false);
  }

  return (
    <main className="min-h-screen bg-[#f4f7f9] text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1500px] flex-col gap-4 px-5 py-5 sm:px-8 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <Link href="/review" className="text-sm font-medium text-teal-700 hover:text-teal-900">← 返回任务列表</Link>
            <h1 className="mt-2 text-2xl font-bold">风筝酒业 · 人工审核</h1>
            <p className="mt-1 text-sm text-slate-500">任务 {taskId} · Customer ID 10467369287105918722 · 谭竞锋（佛山）</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-amber-100 px-3 py-1.5 text-sm font-semibold text-amber-700">待审核</span>
            <button onClick={() => setSaved(true)} className="rounded-lg bg-teal-700 px-5 py-2.5 text-sm font-bold text-white hover:bg-teal-600">
              {saved ? "✓ 已保存审核" : "保存审核结果"}
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1500px] gap-6 px-5 py-6 sm:px-8 lg:grid-cols-[minmax(360px,0.78fr)_minmax(600px,1.22fr)]">
        <aside className="space-y-5 lg:sticky lg:top-5 lg:self-start">
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 px-5 py-4"><h2 className="font-bold">录音列表</h2><p className="mt-1 text-xs text-slate-500">选择录音查看对应转写</p></div>
            <div className="divide-y divide-slate-100">
              {recordings.map((recording) => (
                <button key={recording.id} onClick={() => { setActiveRecording(recording); setCurrentTime(0); setIsPlaying(false); }} className={`flex w-full items-center gap-3 px-5 py-4 text-left ${activeRecording.id === recording.id ? "bg-teal-50" : "hover:bg-slate-50"}`}>
                  <span className={`flex h-9 w-9 items-center justify-center rounded-full ${activeRecording.id === recording.id ? "bg-teal-700 text-white" : "bg-slate-100"}`}>▶</span>
                  <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{recording.name}</span><span className="mt-0.5 block text-xs text-slate-500">{recording.id} · {formatTime(recording.duration)}</span></span>
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-2xl bg-slate-900 p-5 text-white shadow-sm">
            <p className="truncate text-sm font-semibold">{activeRecording.name}</p>
            <div className="mt-5 flex items-center gap-4">
              <button onClick={() => setIsPlaying((value) => !value)} aria-label={isPlaying ? "暂停" : "播放"} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-teal-500 text-lg hover:bg-teal-400">{isPlaying ? "Ⅱ" : "▶"}</button>
              <div className="flex-1">
                <input aria-label="录音进度" type="range" min="0" max={activeRecording.duration} step="0.1" value={currentTime} onChange={(event) => setCurrentTime(Number(event.target.value))} className="w-full accent-teal-400" />
                <div className="mt-1 flex justify-between text-xs text-slate-400"><span>{formatTime(currentTime)}</span><span>{formatTime(activeRecording.duration)}</span></div>
              </div>
            </div>
            <div className="mt-3 h-1 overflow-hidden rounded bg-slate-700"><div className="h-full bg-teal-400" style={{ width: `${progress}%` }} /></div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 px-5 py-4"><h2 className="font-bold">带时间戳转写</h2><p className="mt-1 text-xs text-slate-500">点击任意段落定位录音</p></div>
            <div className="max-h-[470px] space-y-1 overflow-y-auto p-3">
              {transcript.map((line) => (
                <button key={`${line.time}-${line.text}`} onClick={() => seek(line.time)} className={`w-full rounded-lg p-3 text-left transition hover:bg-teal-50 ${Math.abs(currentTime - line.time) < 4 ? "bg-teal-50 ring-1 ring-teal-200" : ""}`}>
                  <div className="mb-1 flex items-center gap-2"><span className="font-mono text-xs font-bold text-teal-700">{formatTime(line.time)}</span><span className="text-xs text-slate-400">{line.speaker}</span></div>
                  <p className="text-sm leading-6 text-slate-700">{line.text}</p>
                </button>
              ))}
            </div>
          </section>
        </aside>

        <section className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="text-lg font-bold">字段审核</h2><p className="mt-1 text-sm text-slate-500">对照 Excel、AI 录音提取结果与原始证据，确认最终值。</p></div><div className="flex flex-wrap gap-2">{Object.values(statusStyle).map((status) => <span key={status.label} className={`rounded-full px-2.5 py-1 text-xs font-semibold ${status.className}`}>{status.label}</span>)}</div></div>
          </div>

          {fields.map((field) => {
            const style = statusStyle[field.status];
            return (
              <article key={field.key} className={`rounded-2xl border border-l-4 border-slate-200 bg-white p-5 shadow-sm ${style.border}`}>
                <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-bold">{field.label}</h3><p className="mt-1 text-xs text-slate-400">AI 置信度 {Math.round(field.confidence * 100)}%</p></div><span className={`rounded-full px-3 py-1 text-xs font-bold ${style.className}`}>{style.label}</span></div>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Excel 值</p><p className="mt-2 text-lg font-bold">{field.excelValue} <span className="text-sm font-normal text-slate-500">{field.unit}</span></p></div>
                  <div className="rounded-xl bg-teal-50 p-4"><p className="text-xs font-semibold uppercase tracking-wide text-teal-600">AI 录音值</p><p className="mt-2 text-lg font-bold text-teal-900">{field.aiValue} <span className="text-sm font-normal text-teal-700">{field.unit}</span></p></div>
                </div>

                {field.evidence && <button onClick={() => seek(field.evidence!.start, field.evidence!.recording)} className="mt-3 w-full rounded-xl border border-slate-200 p-3 text-left hover:border-teal-400 hover:bg-teal-50"><div className="flex flex-wrap items-center gap-2 text-xs"><span className="rounded bg-slate-900 px-2 py-1 font-mono font-bold text-white">▶ {formatTime(field.evidence.start)}–{formatTime(field.evidence.end)}</span><span className="text-slate-400">{field.evidence.recording}</span></div><p className="mt-2 text-sm text-slate-700">“{field.evidence.text}”</p></button>}

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <label className="text-sm font-semibold text-slate-700">人工最终值
                    <div className="mt-1 flex rounded-lg border border-slate-300 bg-white focus-within:border-teal-600"><input value={field.finalValue} onChange={(event) => updateField(field.key, { finalValue: event.target.value, status: "reviewed" })} className="min-w-0 flex-1 rounded-lg px-3 py-2.5 font-normal outline-none" />{field.unit && <span className="border-l border-slate-200 px-3 py-2.5 font-normal text-slate-500">{field.unit}</span>}</div>
                  </label>
                  <label className="text-sm font-semibold text-slate-700">修改原因
                    <input value={field.changeReason} onChange={(event) => updateField(field.key, { changeReason: event.target.value, status: "reviewed" })} placeholder="如有修改，请填写原因" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal outline-none focus:border-teal-600" />
                  </label>
                </div>
              </article>
            );
          })}

          <div className="flex flex-col items-stretch justify-between gap-4 rounded-2xl bg-slate-900 p-5 text-white sm:flex-row sm:items-center"><div><p className="font-bold">审核进度 {fields.filter((field) => field.status === "reviewed" || field.status === "matched").length} / {fields.length}</p><p className="mt-1 text-sm text-slate-400">保存后将记录最终值、修改原因和审核状态。</p></div><button onClick={() => setSaved(true)} className="rounded-lg bg-teal-500 px-6 py-3 font-bold hover:bg-teal-400">{saved ? "✓ 审核结果已保存" : "保存审核结果"}</button></div>
          {saved && <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm font-medium text-emerald-800">模拟保存成功：任务 {taskId} 的人工审核结果已记录。</div>}
        </section>
      </div>
    </main>
  );
}
