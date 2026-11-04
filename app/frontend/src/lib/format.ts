export const fmtTime = (ts: number): string =>
  ts ? new Date(ts * 1000).toLocaleString('vi-VN', { hour12: false, dateStyle: 'medium', timeStyle: 'short' }) : '—';

export const fmtSize = (bytes: number): string =>
  bytes > 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

export function fmtElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export const abbr = (n: number): string => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

export const plural = (n: number, unit: string): string => `${n} ${unit}`; // Vietnamese has no plural form
