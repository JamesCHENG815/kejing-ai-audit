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
