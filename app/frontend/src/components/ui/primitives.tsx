import type { ButtonHTMLAttributes, ReactNode } from 'react';
import type { JobStatus } from '../../api/types';
import { cx } from '../../lib/cx';
import { Icon, type IconName } from './Icon';

type Variant = 'default' | 'primary' | 'danger' | 'ghost';

const BUTTON_BASE =
  'inline-flex items-center justify-center gap-1.5 rounded-md border text-xs font-medium whitespace-nowrap transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45';
const BUTTON_VARIANT: Record<Variant, string> = {
  default: 'border-strong bg-white text-ink hover:enabled:bg-surface2 active:enabled:bg-line',
  primary: 'border-primary bg-primary text-white hover:enabled:bg-primary-hover active:enabled:bg-primary-press',
  danger: 'border-danger bg-danger text-white hover:enabled:bg-danger-hover',
  ghost: 'border-transparent bg-transparent text-ink-2 hover:enabled:border-line hover:enabled:bg-surface2',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: 'sm' | 'md';
  icon?: IconName;
  loading?: boolean;
}

export function Button({ variant = 'default', size = 'md', icon, loading, children, className, disabled, type = 'button', ...rest }: ButtonProps) {
  return (
    <button {...rest} type={type} disabled={disabled || loading}
      className={cx(BUTTON_BASE, BUTTON_VARIANT[variant], size === 'sm' ? 'h-7 px-2.5' : 'h-8 px-3.5', className)}>
      {loading ? <Spinner /> : icon ? <Icon name={icon} size={size === 'sm' ? 16 : 18} /> : null}
      {children}
    </button>
  );
}

export function IconButton({ icon, label, size = 'sm', className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { icon: IconName; label: string; size?: 'sm' | 'md' }) {
  return (
    <button type="button" {...rest} aria-label={label} title={label}
      className={cx(BUTTON_BASE, BUTTON_VARIANT.ghost, 'p-0', size === 'md' ? 'size-8' : 'size-7', className)}>
      <Icon name={icon} size={16} />
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <span aria-hidden="true" className={cx('size-4 animate-spin rounded-full border-2 border-line border-t-primary', className)} />;
}

type Tone = 'ok' | 'warn' | 'error' | 'muted' | 'info';
const TONE: Record<Tone, string> = {
  ok: 'border-ok-line bg-ok-soft text-ok',
  info: 'border-primary-line bg-primary-soft text-primary',
  error: 'border-danger-line bg-danger-soft text-danger',
  warn: 'border-warn-line bg-warn-soft text-warn',
  muted: 'border-line bg-surface2 text-mute',
};
const STATUS_TONE: Record<JobStatus, Tone> = { pending: 'info', running: 'info', done: 'ok', failed: 'error' };
const STATUS_LABEL: Record<JobStatus, string> = { pending: 'Chờ xử lý', running: 'Đang xử lý', done: 'Hoàn tất', failed: 'Lỗi' };

/** Pill status tag with a round dot. */
export function Badge({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title}
      className={cx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium leading-normal before:size-1.5 before:rounded-full before:bg-current before:content-[""]', TONE[tone])}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: JobStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="segmented inline-flex max-w-full overflow-x-auto rounded-md border border-strong bg-white">
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}
          className="h-7 flex-none whitespace-nowrap border-r border-line px-3 text-xs font-medium text-ink-2 last:border-r-0 hover:bg-surface2 aria-pressed:bg-primary aria-pressed:text-white aria-pressed:hover:bg-primary">
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** A bordered panel with an optional title strip. */
export function Panel({ title, actions, children, className, label, fill }: { title?: string; actions?: ReactNode; children: ReactNode; className?: string; label?: string; fill?: boolean }) {
  return (
    <section aria-label={label ?? title} className={cx('min-w-0 rounded-lg border border-line bg-white shadow-panel', fill && 'flex min-h-0 flex-1 flex-col', className)}>
      {title && (
        <div className="flex min-h-11 flex-none items-center justify-between gap-3 rounded-t-lg border-b border-line bg-chrome px-4 py-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-mute">{title}</h2>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1.5 px-5 py-9 text-center text-mute">
      <strong className="text-[14px] text-ink">{title}</strong>
      {children}
      {action}
    </div>
  );
}

/** Quiet readout tile: small label, light large figure; tone only tints the figure and adds a small dot. */
export function Kpi({ label, value, tone }: { label: string; value: ReactNode; tone?: 'ok' | 'warn' }) {
  return (
    <div className="kpi rounded-lg border border-line bg-white px-4 py-3">
      <div className="l text-xs text-mute">{label}</div>
      <div className={cx('v mt-0.5 flex items-center gap-2 text-[28px] font-semibold leading-tight tabular-nums', tone === 'ok' && 'text-ok', tone === 'warn' && 'text-warn', !tone && 'text-ink')}>
        {tone && <span aria-hidden="true" className={cx('size-2 rounded-full', tone === 'ok' ? 'bg-ok' : 'bg-warn-led')} />}
        {value}
      </div>
    </div>
  );
}

export const PAGE_SIZES = [10, 25, 50, 100];

/** Footer pager: "1–10 / 42", rows per page, previous / next. Page is 1-based and clamped by the caller. */
export function Pagination({ page, pageSize, total, onPage, onPageSize }: {
  page: number; pageSize: number; total: number; onPage: (p: number) => void; onPageSize: (n: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav aria-label="Phân trang" className="flex flex-none flex-wrap items-center justify-between gap-3 border-t border-line bg-chrome px-3 py-2 text-xs text-mute">
      <label className="flex items-center gap-2">
        Số dòng mỗi trang
        <select value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))}
          className="h-[26px] rounded border border-strong bg-white px-1.5 text-ink focus:border-primary focus:outline-none focus:shadow-ring">
          {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <span className="font-mono tabular-nums" aria-live="polite">{from}–{to} / {total}</span>
      <div className="flex items-center gap-1">
        <IconButton icon="chevronLeft" label="Trang trước" disabled={page <= 1} onClick={() => onPage(page - 1)} />
        <span className="min-w-14 text-center font-mono tabular-nums">{page} / {pages}</span>
        <IconButton icon="chevronRight" label="Trang sau" disabled={page >= pages} onClick={() => onPage(page + 1)} />
      </div>
    </nav>
  );
}

export function Skeleton({ w = '100%', h = 16 }: { w?: number | string; h?: number }) {
  return <div aria-hidden="true" style={{ width: w, height: h }} className="animate-shimmer bg-gradient-to-r from-surface2 via-line to-surface2 bg-[length:200%_100%]" />;
}
