"use client";

import { ChangeEvent, DragEvent, useMemo, useRef, useState } from "react";
import AppShell from "@/components/app-shell";
import { API_BASE_URL, apiRequest, uploadWithProgress } from "@/lib/api";

type Batch = { id: number; original_filename: string; status: string; task_count: number };
type Recording = { id: number; filename: string; recommended: boolean; confirmed: boolean };
type Task = { id: number; customer_id: string; store_name: string; visitor: string; recordings: Recording[] };
type Matches = { batch_id: number; status: string; tasks: Task[]; unassigned_recordings: Recording[] };

const MAX_EXCEL = 50 * 1024 * 1024;
const MAX_AUDIO = 100 * 1024 * 1024;
const excelTypes = ["xlsx", "xlsm"];
const audioTypes = ["m4a", "mp3", "wav", "aac", "flac"];

function ext(name: string) { return name.split(".").pop()?.toLowerCase() ?? ""; }
function sizeLabel(bytes: number) { return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`; }
function errorText(error: unknown) { return error instanceof Error ? error.message : "操作失败，请稍后重试"; }

export default function ImportPage() {
  const excelRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLInputElement>(null);
  const [excel, setExcel] = useState<File | null>(null);
  const [audios, setAudios] = useState<File[]>([]);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [matches, setMatches] = useState<Matches | null>(null);
  const [assignments, setAssignments] = useState<Record<number, number>>({});
  const [dragging, setDragging] = useState<"excel" | "audio" | null>(null);
  const [busy, setBusy] = useState<"excel" | "audio" | "save" | "submit" | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [matchesExpanded, setMatchesExpanded] = useState(false);

  const recordings = useMemo(() => matches ? [...matches.tasks.flatMap((task) => task.recordings), ...matches.unassigned_recordings] : [], [matches]);
  const visibleRecordings = matchesExpanded ? recordings : recordings.slice(0, 3);
  const submitted = batch?.status === "submitted" || batch?.status === "analyzed";

  function startNextBatch() {
    setExcel(null); setAudios([]); setBatch(null); setMatches(null); setAssignments({});
    setDragging(null); setBusy(null); setProgress(0); setError(""); setNotice(""); setMatchesExpanded(false);
    if (excelRef.current) excelRef.current.value = "";
    if (audioRef.current) audioRef.current.value = "";
  }

  function chooseExcel(file?: File) {
    if (!file) return;
    if (!excelTypes.includes(ext(file.name))) return setError("Excel 仅支持 .xlsx 或 .xlsm 格式");
    if (file.size > MAX_EXCEL) return setError("Excel 文件不能超过 50 MB");
    setExcel(file); setBatch(null); setMatches(null); setError(""); setNotice(""); setMatchesExpanded(false);
  }

  function chooseAudios(files: FileList | File[]) {
    const selected = Array.from(files);
    const invalid = selected.find((file) => !audioTypes.includes(ext(file.name)) || file.size > MAX_AUDIO);
    if (invalid) return setError(`${invalid.name} 格式不支持或超过 100 MB`);
    setAudios((current) => [...current, ...selected.filter((file) => !current.some((item) => item.name === file.name))]);
    setError("");
  }

  async function uploadExcel() {
    if (!excel) return;
    setBusy("excel"); setProgress(0); setError(""); setNotice("");
    try {
      const form = new FormData(); form.append("file", excel);
      const created = await uploadWithProgress<Batch>("/api/import-batches", form, setProgress);
      setBatch(created); setNotice(`成功解析 ${created.task_count} 家门店，请继续上传录音。`);
    } catch (err) { setError(errorText(err)); } finally { setBusy(null); }
  }

  async function loadMatches(batchId: number) {
    const data = await apiRequest<Matches>(`/api/import-batches/${batchId}/matches`);
    setMatches(data);
    const next: Record<number, number> = {};
    data.tasks.forEach((task) => task.recordings.forEach((recording) => { next[recording.id] = task.id; }));
    setAssignments(next);
  }

  async function uploadAudios() {
    if (!batch || !audios.length) return;
    setBusy("audio"); setProgress(0); setError("");
    try {
      const form = new FormData(); audios.forEach((file) => form.append("files", file));
      const result = await uploadWithProgress<{ uploaded_count: number; matched_count: number }>(`/api/import-batches/${batch.id}/recordings`, form, setProgress);
      await loadMatches(batch.id); setAudios([]); setNotice(`已上传 ${result.uploaded_count} 段录音，系统推荐匹配 ${result.matched_count} 段。`);
    } catch (err) { setError(errorText(err)); } finally { setBusy(null); }
  }

  async function removeRecording(id: number) {
    if (!batch) return;
    setError("");
    try {
      await apiRequest(`/api/import-batches/${batch.id}/recordings/${id}`, { method: "DELETE" });
      await loadMatches(batch.id); setNotice("录音已删除。");
    } catch (err) { setError(errorText(err)); }
  }

  async function saveMatches(submit = false) {
    if (!batch || !recordings.length) return;
    const missing = recordings.filter((recording) => !assignments[recording.id]);
    if (missing.length) return setError(`仍有 ${missing.length} 段录音未关联门店`);
    setBusy(submit ? "submit" : "save"); setError("");
    try {
      await apiRequest(`/api/import-batches/${batch.id}/matches`, { method: "PUT", body: JSON.stringify({ assignments: recordings.map((recording) => ({ recording_id: recording.id, task_id: assignments[recording.id], confirmed: true })) }) });
      if (submit) {
        await apiRequest(`/api/import-batches/${batch.id}/submit`, { method: "POST" });
        setBatch((current) => current ? { ...current, status: "submitted" } : current);
        setAudios([]); setMatchesExpanded(false);
        setNotice("提交成功，AI 将在后台自动分析。你现在可以继续导入下一批。");
      } else {
        await loadMatches(batch.id); setNotice("录音与门店关联已保存。");
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  return <AppShell active="import"><main className="mx-auto max-w-[1680px] px-5 py-8 sm:px-8">
    <div className="mb-8 flex flex-col gap-3 md:flex-row md:items-end md:justify-between"><div><p className="text-xs font-black tracking-[0.2em] text-[#137161]">IMPORT WORKSPACE</p><h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">把拜访资料变成可审核任务</h1><p className="mt-2 max-w-2xl text-slate-500">依次上传 SFA Excel 与门店录音，核对系统推荐关系后提交审核任务。</p></div><div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500">API · <span className="font-mono text-xs text-slate-800">{API_BASE_URL}</span></div></div>

    <div className="mb-7 grid grid-cols-3 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">{["上传 Excel", "关联录音", "提交任务"].map((label, index) => { const active = index === 0 ? !batch : index === 1 ? batch && !submitted : submitted; return <div key={label} className={`border-r border-slate-100 px-3 py-4 text-center text-sm font-bold last:border-0 ${active ? "bg-[#eaf5f1] text-[#0d5b4f]" : "text-slate-400"}`}><span className={`mr-2 inline-flex h-6 w-6 items-center justify-center rounded-full ${active ? "bg-[#0d5b4f] text-white" : "bg-slate-100"}`}>{index + 1}</span>{label}</div>; })}</div>

    {(error || notice) && <div role={error ? "alert" : "status"} className={`mb-5 flex items-start justify-between gap-4 rounded-xl border px-4 py-3 text-sm font-semibold ${error ? "border-rose-200 bg-rose-50 text-rose-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}><span>{error || notice}</span><button onClick={() => { setError(""); setNotice(""); }} aria-label="关闭提示">×</button></div>}

    <div className="grid items-stretch gap-5 xl:grid-cols-3">
    <section className={`min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6 ${submitted ? "pointer-events-none opacity-60" : ""}`}><div className="flex items-start justify-between gap-4"><div><span className="text-xs font-black text-[#137161]">STEP 01</span><h2 className="mt-1 text-xl font-black">上传 SFA Excel</h2><p className="mt-1 text-sm text-slate-500">支持 .xlsx / .xlsm，单个文件不超过 50 MB。</p></div>{batch && <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">解析成功</span>}</div>
      <div onDragOver={(event) => event.preventDefault()} onDragEnter={() => setDragging("excel")} onDragLeave={() => setDragging(null)} onDrop={(event: DragEvent<HTMLDivElement>) => { event.preventDefault(); setDragging(null); chooseExcel(event.dataTransfer.files[0]); }} onClick={() => excelRef.current?.click()} className={`mt-5 cursor-pointer rounded-2xl border-2 border-dashed p-7 text-center transition ${dragging === "excel" ? "border-[#137161] bg-[#eaf5f1]" : "border-slate-300 bg-slate-50 hover:border-[#137161]"}`}><input ref={excelRef} type="file" accept=".xlsx,.xlsm" className="hidden" onChange={(event: ChangeEvent<HTMLInputElement>) => chooseExcel(event.target.files?.[0])}/><span className="text-3xl">⇧</span><p className="mt-2 font-bold">{excel?.name ?? "拖拽 Excel 到此处，或点击选择"}</p>{excel && <p className="mt-1 text-xs text-slate-500">{sizeLabel(excel.size)}</p>}</div>
      {busy === "excel" && <div className="mt-4"><div className="mb-1 flex justify-between text-xs font-bold text-slate-500"><span>上传并解析中</span><span>{progress}%</span></div><div className="h-2 rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#137161] transition-all" style={{ width: `${progress}%` }}/></div></div>}
      <div className="mt-5 flex justify-end"><button disabled={!excel || busy !== null} onClick={uploadExcel} className="rounded-xl bg-[#0d5b4f] px-6 py-3 font-bold text-white hover:bg-[#137161] disabled:cursor-not-allowed disabled:bg-slate-300">{busy === "excel" ? "正在处理…" : batch ? "重新导入" : "上传并解析"}</button></div>
      {batch && <dl className="mt-6 grid gap-3 border-t border-slate-100 pt-6 sm:grid-cols-4"><div className="rounded-xl bg-slate-50 p-4"><dt className="text-xs text-slate-500">批次 ID</dt><dd className="mt-1 text-xl font-black">#{batch.id}</dd></div><div className="rounded-xl bg-slate-50 p-4 sm:col-span-2"><dt className="text-xs text-slate-500">文件名</dt><dd className="mt-1 truncate font-bold">{batch.original_filename}</dd></div><div className="rounded-xl bg-slate-50 p-4"><dt className="text-xs text-slate-500">解析结果</dt><dd className="mt-1 font-bold">{batch.task_count} 家门店</dd></div></dl>}
    </section>

    <section className={`min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6 ${!batch || submitted ? "pointer-events-none opacity-50" : ""}`}><div><span className="text-xs font-black text-[#137161]">STEP 02</span><h2 className="mt-1 text-xl font-black">上传并关联录音</h2><p className="mt-1 text-sm text-slate-500">支持批量上传；系统按文件名推荐门店，你可以手动调整。</p></div>
      <div onDragOver={(event) => event.preventDefault()} onDrop={(event: DragEvent<HTMLDivElement>) => { event.preventDefault(); chooseAudios(event.dataTransfer.files); }} onClick={() => audioRef.current?.click()} className="mt-5 cursor-pointer rounded-xl border border-dashed border-slate-300 bg-slate-50 px-5 py-5 text-center hover:border-[#137161]"><input ref={audioRef} type="file" multiple accept="audio/*,.m4a,.aac,.flac" className="hidden" onChange={(event) => event.target.files && chooseAudios(event.target.files)}/><p className="font-bold">＋ 选择或拖入多段录音</p><p className="mt-1 text-xs text-slate-500">每段最大 100 MB</p></div>
      {audios.length > 0 && <div className="mt-4 rounded-xl border border-slate-200"><div className="flex items-center justify-between border-b border-slate-100 px-4 py-3"><span className="text-sm font-bold">待上传 {audios.length} 段</span><button onClick={() => setAudios([])} className="text-xs font-bold text-rose-600">清空</button></div>{audios.map((file) => <div key={file.name} className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 text-sm last:border-0"><span className="truncate">♪ {file.name}</span><span className="shrink-0 text-xs text-slate-400">{sizeLabel(file.size)}</span></div>)}</div>}
      {busy === "audio" && <div className="mt-4"><div className="mb-1 flex justify-between text-xs font-bold text-slate-500"><span>录音上传中</span><span>{progress}%</span></div><div className="h-2 rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#137161]" style={{ width: `${progress}%` }}/></div></div>}
      <div className="mt-4 flex justify-end"><button disabled={!audios.length || busy !== null} onClick={uploadAudios} className="rounded-xl border border-[#0d5b4f] px-5 py-2.5 text-sm font-bold text-[#0d5b4f] disabled:border-slate-200 disabled:text-slate-300">上传录音</button></div>

      {matches && <div className="mt-7 overflow-hidden rounded-xl border border-slate-200"><div className="flex items-center justify-between gap-3 bg-slate-50 px-4 py-3 text-xs font-black text-slate-500"><span>录音与关联门店 · {recordings.length} 段</span>{recordings.length > 3 && !submitted && <button onClick={() => setMatchesExpanded((value) => !value)} className="shrink-0 font-black text-[#137161]">{matchesExpanded ? "收起" : `展开全部 ${recordings.length} 段`}</button>}</div><div className="max-h-[360px] divide-y divide-slate-100 overflow-y-auto">{visibleRecordings.map((recording) => <div key={recording.id} className="grid gap-3 px-4 py-4"><div className="min-w-0"><p className="truncate text-sm font-bold">♪ {recording.filename}</p><p className="mt-1 text-xs text-slate-400">{recording.recommended ? "系统推荐" : "待人工关联"}</p></div><select value={assignments[recording.id] ?? ""} onChange={(event) => setAssignments((current) => ({ ...current, [recording.id]: Number(event.target.value) }))} className="min-w-0 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#137161]"><option value="">选择门店任务</option>{matches.tasks.map((task) => <option key={task.id} value={task.id}>{task.store_name} · {task.customer_id}</option>)}</select><button onClick={() => removeRecording(recording.id)} disabled={batch?.status === "submitted"} className="justify-self-start rounded-lg px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-50 disabled:text-slate-300">删除</button></div>)}</div></div>}
    </section>

    <section className={`flex min-w-0 flex-col justify-start gap-6 rounded-2xl bg-[#102c28] p-6 text-white shadow-lg ${!recordings.length && !submitted ? "opacity-60" : ""}`}><div><span className="text-xs font-black tracking-[0.16em] text-emerald-300">STEP 03</span><h2 className="mt-1 text-xl font-black">{submitted ? "任务提交成功" : "确认关联并提交任务"}</h2><p className="mt-1 text-sm text-slate-300">{submitted ? `批次 #${batch.id} 已进入 AI 分析队列，无需在此等待。` : recordings.length ? `${recordings.length} 段录音 · ${Object.keys(assignments).length} 段已关联` : "上传录音后可提交"}</p></div>{submitted ? <div className="flex flex-col gap-4"><div className="rounded-xl border border-emerald-300/30 bg-emerald-300/10 p-4"><p className="font-black text-emerald-300">✓ 提交成功</p><p className="mt-1 text-sm text-slate-300">AI 将在后台自动分析，分析结果会进入经理审核工作台。</p></div><button onClick={startNextBatch} className="rounded-xl bg-emerald-400 px-5 py-3 text-sm font-black text-[#102c28] hover:bg-emerald-300">继续导入下一批 →</button></div> : <div className="flex flex-col gap-3 sm:flex-row xl:flex-col"><button disabled={!recordings.length || busy !== null} onClick={() => saveMatches(false)} className="rounded-xl border border-white/30 px-4 py-3 text-sm font-bold hover:bg-white/10 disabled:opacity-40">保存关联</button><button disabled={!recordings.length || busy !== null} onClick={() => saveMatches(true)} className="rounded-xl bg-emerald-400 px-5 py-3 text-sm font-black text-[#102c28] hover:bg-emerald-300 disabled:bg-slate-600 disabled:text-slate-300">{busy === "submit" ? "提交中…" : "提交审核任务 →"}</button></div>}</section>
    </div>
  </main></AppShell>;
}
