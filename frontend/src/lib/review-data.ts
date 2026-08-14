export type TaskStatus = "analyzing" | "analysis_failed" | "pending" | "reviewing" | "completed";
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
  address?: string;
  visitDate?: string;
};

export type ReviewField = {
  key: string;
  label: string;
  excel: string;
  ai: string;
  unit?: string;
  confidence: number;
  status: FieldStatus;
  final: string;
  reason: string;
  confirmed: boolean;
  evidence?: { recordingId: string; start: number; end: number; text: string };
};

export type ReviewModule = {
  id: "last-year" | "current-year" | "products" | "other";
  title: string;
  description: string;
  groups: ReviewField[][];
};

const SALES_BRANDS = ["马爹利", "轩尼诗", "人头马", "白酒", "威士忌"];
const IMAGE_MARKERS = ["图片", "照片", "影像", "picture", "photo", "image"];

export function isImageReviewField(name: string) {
  const normalized = name.normalize("NFKC").toLowerCase();
  return IMAGE_MARKERS.some((marker) => normalized.includes(marker));
}

function brandIndex(name: string) {
  const index = SALES_BRANDS.findIndex((brand) => name.includes(brand));
  return index < 0 ? Number.MAX_SAFE_INTEGER : index;
}

function productIndex(name: string) {
  return Number(name.match(/^畅销产品(\d+)/)?.[1] ?? Number.MAX_SAFE_INTEGER);
}

function productPartIndex(name: string) {
  if (/产品瓶数$/.test(name)) return 1;
  if (/进货价$/.test(name)) return 2;
  return 0;
}

export function buildReviewModules(source: ReviewField[]): ReviewModule[] {
  const fields = source.filter((field) => !isImageReviewField(field.key) && !isImageReviewField(field.label));
  const lastYear = fields
    .filter((field) => field.key.includes("上一个自然年零售金额") || field.key.includes("去年销售额"))
    .sort((left, right) => brandIndex(left.key) - brandIndex(right.key));
  const currentYear = fields
    .filter((field) => field.key.includes("今年截止到上个月零售金额") || field.key.includes("今年截至上月销售额"))
    .sort((left, right) => brandIndex(left.key) - brandIndex(right.key));
  const productFields = fields.filter((field) => /^畅销产品\d+(?:产品瓶数|进货价)?$/.test(field.key));
  const productNumbers = [...new Set(productFields.map((field) => productIndex(field.key)))].sort((a, b) => a - b);
  const products = productNumbers.map((index) =>
    productFields
      .filter((field) => productIndex(field.key) === index)
      .sort((left, right) => productPartIndex(left.key) - productPartIndex(right.key)),
  );
  const used = new Set([...lastYear, ...currentYear, ...productFields].map((field) => field.key));
  const other = fields.filter((field) => !used.has(field.key));

  return [
    { id: "last-year", title: "A. 去年销售额", description: "按五大品类核对上一自然年零售金额", groups: lastYear.map((field) => [field]) },
    { id: "current-year", title: "B. 今年截至上月销售额", description: "按五大品类核对今年累计零售金额", groups: currentYear.map((field) => [field]) },
    { id: "products", title: "C. 畅销品牌", description: "每个产品将名称、进货价格和上月零售瓶数组合审核", groups: products },
    { id: "other", title: "D. 其他问题", description: "宴会场次、团购客户、同比及其他经营信息", groups: other.map((field) => [field]) },
  ];
}

export const taskStatusMeta: Record<TaskStatus, { label: string; className: string }> = {
  analyzing: { label: "AI 分析中", className: "bg-blue-50 text-blue-700 ring-blue-200" },
  analysis_failed: { label: "AI 分析失败", className: "bg-rose-50 text-rose-700 ring-rose-200" },
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
