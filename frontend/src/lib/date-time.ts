const BEIJING_TIME_ZONE = "Asia/Shanghai";

const beijingDateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: BEIJING_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function parseApiDateTime(value: string) {
  const normalized = value.trim();
  const hasExplicitTimeZone = /(Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  const isDateTimeWithoutTimeZone = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(normalized);

  // The API stores timestamps in UTC but can return them without an offset.
  // Add the UTC designator so browsers do not interpret them in their local zone.
  const date = new Date(
    isDateTimeWithoutTimeZone && !hasExplicitTimeZone
      ? `${normalized.replace(" ", "T")}Z`
      : normalized,
  );

  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatBeijingDateTime(value: string | Date) {
  const date = value instanceof Date ? value : parseApiDateTime(value);
  if (!date || Number.isNaN(date.getTime())) return typeof value === "string" ? value : "—";

  const parts = Object.fromEntries(
    beijingDateTimeFormatter
      .formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );

  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}
