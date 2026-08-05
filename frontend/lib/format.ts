export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(d);
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return "—";
  const diff = Date.now() - d;
  const abs = Math.abs(diff);
  if (abs < 60_000) return "刚刚";
  const units: [number, string][] = [
    [60_000, " 分钟"],
    [3_600_000, " 小时"],
    [86_400_000, " 天"],
  ];
  for (const [ms, label] of units) {
    if (abs < ms * 60) {
      const v = Math.round(abs / ms);
      return `${v}${label}前`;
    }
  }
  return formatDateTime(iso);
}

export function shortId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}