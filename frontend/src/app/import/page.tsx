"use client";

import { ChangeEvent, DragEvent, useMemo, useRef, useState } from "react";

const stores = [
  {
    customerId: "9804729391770344743",
    name: "品惠行烟酒（天景大厦店）",
    visitor: "郑之源（广州）",
    recordings: ["品惠行烟酒(天景大厦店)(1).m4a"],
  },
  {
    customerId: "10467369287105918722",
    name: "风筝酒业",
    visitor: "谭竞锋（佛山）",
    recordings: ["风筝酒业.m4a", "风筝酒业(1).m4a"],
  },
  {
    customerId: "10094564054480562271",
    name: "宜嘉真烟酒行（恒福新里程分店）",
    visitor: "谭竞锋（佛山）",
    recordings: ["宜嘉真烟酒.m4a", "宜嘉珍烟酒行.m4a"],
  },
  {
    customerId: "1503940623623717731",
    name: "明智酒业（三水雅居乐花园雅怡居店）",
    visitor: "谭竞锋（佛山）",
    recordings: ["明智酒业(2).m4a", "明智酒业(3).m4a"],
  },
  {
    customerId: "12623470005627425111",
    name: "和裕商行（九鸿世纪广场店）",
    visitor: "文观伙（深圳）",
    recordings: ["录音信息--和裕商行洋酒市場调研_.m4a"],
  },
];

const allRecordings = stores.flatMap((store) => store.recordings);

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-7 w-7 fill-none stroke-current stroke-2">
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />
    </svg>
  );
}

export default function ImportPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [selected, setSelected] = useState<string[]>(allRecordings);
  const [assignments, setAssignments] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      stores.flatMap((store) =>
        store.recordings.map((recording) => [recording, store.customerId]),
      ),
    ),
  );
  const [confirmed, setConfirmed] = useState(false);

  const selectedCountByStore = useMemo(
    () =>
      Object.fromEntries(
        stores.map((store) => [
          store.customerId,
          selected.filter(
            (recording) => assignments[recording] === store.customerId,
          ).length,
        ]),
      ),
    [assignments, selected],
  );

  function acceptFile(file?: File) {
    if (!file) return;
    setFileName(file.name);
    setConfirmed(false);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    acceptFile(event.target.files?.[0]);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    acceptFile(event.dataTransfer.files?.[0]);
  }

  function toggleRecording(recording: string) {
    setSelected((current) =>
      current.includes(recording)
        ? current.filter((item) => item !== recording)
        : [...current, recording],
    );
    setConfirmed(false);
  }

  const allSelected = selected.length === allRecordings.length;

  return (
    <main className="min-h-screen bg-[#f4f7f9] text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8">
          <div>
            <p className="text-sm font-semibold tracking-[0.18em] text-teal-700">KEJING AI AUDIT</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">导入拜访数据</h1>
          </div>
          <div className="hidden items-center gap-2 rounded-full bg-teal-50 px-4 py-2 text-sm font-medium text-teal-800 sm:flex">
            <span className="h-2 w-2 rounded-full bg-teal-500" />
            新建审核任务
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl space-y-6 px-5 py-8 sm:px-8">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
          <div className="mb-5 flex items-start gap-3">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-teal-700 text-sm font-bold text-white">1</span>
            <div>
              <h2 className="text-lg font-bold">上传 SFA Excel</h2>
              <p className="mt-1 text-sm text-slate-500">上传门店拜访明细，系统将自动解析客户信息。</p>
            </div>
          </div>

          <div
            onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition ${
              isDragging ? "border-teal-600 bg-teal-50" : "border-slate-300 bg-slate-50 hover:border-teal-500 hover:bg-teal-50/50"
            }`}
          >
            <input ref={inputRef} type="file" accept=".xlsx,.xls,.csv" onChange={handleFileChange} className="hidden" />
            <span className="mb-3 rounded-full bg-white p-3 text-teal-700 shadow-sm"><UploadIcon /></span>
            {fileName ? (
              <>
                <p className="font-semibold text-teal-800">{fileName}</p>
                <p className="mt-1 text-sm text-slate-500">文件已就绪 · 点击可重新选择</p>
              </>
            ) : (
              <>
                <p className="font-semibold">拖拽 Excel 到这里，或点击选择文件</p>
                <p className="mt-1 text-sm text-slate-500">支持 .xlsx、.xls、.csv</p>
              </>
            )}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
          <div className="mb-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
            <div className="flex items-start gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-teal-700 text-sm font-bold text-white">2</span>
              <div>
                <h2 className="text-lg font-bold">确认门店与录音关联</h2>
                <p className="mt-1 text-sm text-slate-500">已解析 5 家门店，推荐匹配 8 段录音。可手动调整归属。</p>
              </div>
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-slate-700">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={() => { setSelected(allSelected ? [] : allRecordings); setConfirmed(false); }}
                className="h-4 w-4 accent-teal-700"
              />
              全选 8 段录音
            </label>
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-200">
            <div className="hidden grid-cols-[minmax(260px,1.25fr)_minmax(260px,1fr)_120px] bg-slate-50 px-5 py-3 text-xs font-bold uppercase tracking-wider text-slate-500 md:grid">
              <span>门店信息</span><span>推荐录音 / 调整关联</span><span className="text-right">状态</span>
            </div>
            <div className="divide-y divide-slate-200">
              {stores.map((store) => (
                <div key={store.customerId} className="grid gap-5 px-5 py-5 md:grid-cols-[minmax(260px,1.25fr)_minmax(260px,1fr)_120px] md:items-center">
                  <div>
                    <h3 className="font-bold text-slate-900">{store.name}</h3>
                    <p className="mt-1 text-sm text-slate-500">拜访人：{store.visitor}</p>
                    <p className="mt-1 font-mono text-xs text-slate-400">Customer ID · {store.customerId}</p>
                  </div>
                  <div className="space-y-3">
                    {store.recordings.map((recording) => (
                      <div key={recording} className="flex items-start gap-3">
                        <input
                          aria-label={`选择 ${recording}`}
                          type="checkbox"
                          checked={selected.includes(recording)}
                          onChange={() => toggleRecording(recording)}
                          className="mt-2 h-4 w-4 shrink-0 accent-teal-700"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium" title={recording}>🎙️ {recording}</p>
                          <select
                            aria-label={`调整 ${recording} 的关联门店`}
                            value={assignments[recording]}
                            onChange={(event) => { setAssignments((current) => ({ ...current, [recording]: event.target.value })); setConfirmed(false); }}
                            className="mt-1.5 w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-600 outline-none focus:border-teal-600"
                          >
                            {stores.map((option) => <option key={option.customerId} value={option.customerId}>{option.name}</option>)}
                          </select>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="md:text-right">
                    <span className="inline-flex rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                      已关联 {selectedCountByStore[store.customerId] ?? 0} 段
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="flex flex-col items-stretch justify-between gap-4 rounded-2xl bg-slate-900 px-6 py-5 text-white shadow-lg sm:flex-row sm:items-center">
          <div>
            <p className="font-bold">共 5 家门店 · 已选择 {selected.length} / 8 段录音</p>
            <p className="mt-1 text-sm text-slate-400">确认后将创建分析任务，当前阶段使用模拟数据。</p>
          </div>
          <button
            type="button"
            disabled={selected.length === 0}
            onClick={() => setConfirmed(true)}
            className="rounded-lg bg-teal-500 px-6 py-3 font-bold text-white transition hover:bg-teal-400 disabled:cursor-not-allowed disabled:bg-slate-600"
          >
            {confirmed ? "✓ 已提交分析" : "确认关联并开始分析"}
          </button>
        </section>

        {confirmed && (
          <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm font-medium text-emerald-800">
            关联已确认：5 家门店和 {selected.length} 段录音已进入模拟分析队列。
          </div>
        )}
      </div>
    </main>
  );
}
