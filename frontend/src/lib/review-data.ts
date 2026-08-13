export type TaskStatus = "pending" | "reviewing" | "completed";
export type FieldStatus = "matched" | "pending" | "conflict" | "missing";

export type ReviewTask = {
  id: string;
  batchId: number;
  customerId: string;
  store: string;
  visitor: string;
  status: TaskStatus;
  updatedAt: string;
  stats: Record<FieldStatus, number>;
};

export const reviewTasks: ReviewTask[] = [
  { id: "1", batchId: 1, customerId: "9804729391770344743", store: "品惠行烟酒（天景大厦店）", visitor: "郑之源（广州）", status: "pending", updatedAt: "2026-08-13 16:42", stats: { matched: 7, pending: 2, conflict: 1, missing: 1 } },
  { id: "2", batchId: 1, customerId: "10467369287105918722", store: "风筝酒业", visitor: "谭竞锋（佛山）", status: "reviewing", updatedAt: "2026-08-13 16:38", stats: { matched: 6, pending: 1, conflict: 2, missing: 1 } },
  { id: "3", batchId: 1, customerId: "10094564054480562271", store: "宜嘉真烟酒行（恒福新里程分店）", visitor: "谭竞锋（佛山）", status: "pending", updatedAt: "2026-08-13 16:31", stats: { matched: 8, pending: 1, conflict: 0, missing: 1 } },
  { id: "4", batchId: 1, customerId: "1503940623623717731", store: "明智酒业（三水雅居乐花园雅怡居店）", visitor: "谭竞锋（佛山）", status: "completed", updatedAt: "2026-08-13 16:20", stats: { matched: 9, pending: 0, conflict: 0, missing: 1 } },
  { id: "5", batchId: 1, customerId: "12623470005627425111", store: "和裕商行（九鸿世纪广场店）", visitor: "文观伙（深圳）", status: "completed", updatedAt: "2026-08-13 16:08", stats: { matched: 8, pending: 0, conflict: 0, missing: 2 } },
];

export const taskStatusMeta: Record<TaskStatus, { label: string; className: string }> = {
  pending: { label: "待审核", className: "bg-amber-50 text-amber-700 ring-amber-200" },
  reviewing: { label: "审核中", className: "bg-blue-50 text-blue-700 ring-blue-200" },
  completed: { label: "已完成", className: "bg-emerald-50 text-emerald-700 ring-emerald-200" },
};

export const fieldStatusMeta: Record<FieldStatus, { label: string; dot: string; className: string }> = {
  matched: { label: "一致", dot: "bg-emerald-500", className: "bg-emerald-50 text-emerald-700" },
  pending: { label: "待确认", dot: "bg-amber-400", className: "bg-amber-50 text-amber-700" },
  conflict: { label: "冲突", dot: "bg-rose-500", className: "bg-rose-50 text-rose-700" },
  missing: { label: "缺失", dot: "bg-slate-400", className: "bg-slate-100 text-slate-600" },
};
