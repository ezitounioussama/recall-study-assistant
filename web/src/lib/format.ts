/** Human forms of the numbers the API hands back. */

/** 60 → "1m", 5400 → "1.5h", 172800 → "2d", 2592000 → "1mo". */
export function formatInterval(seconds: number): string {
  if (seconds < 60) return "<1m";
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 24) return `${hours % 1 === 0 ? hours : hours.toFixed(1)}h`;
  const days = hours / 24;
  if (days < 30) return `${Math.round(days)}d`;
  const months = days / 30;
  if (months < 12) return `${months % 1 === 0 ? months : months.toFixed(1)}mo`;
  return `${(days / 365).toFixed(1)}y`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

/** "in 3d", "in 2h", or "now" for a due timestamp. */
export function formatDue(iso: string | null): string {
  if (!iso) return "—";
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
  if (seconds <= 0) return "now";
  return `in ${formatInterval(seconds)}`;
}
