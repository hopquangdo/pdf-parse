import { forwardRef, useId, useState, type InputHTMLAttributes, type ReactNode } from 'react';
import { cx } from '../../lib/cx';
import { Icon } from './Icon';

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  /** Adds a show / hide toggle (for password fields). */
  revealable?: boolean;
}

/** Labelled input with hint and error text wired up for assistive technology. */
export const TextField = forwardRef<HTMLInputElement, Props>(function TextField(
  { label, hint, error, revealable, className, type = 'text', ...rest }, ref,
) {
  const id = useId();
  const [shown, setShown] = useState(false);
  const describedBy = [hint && `${id}-hint`, error && `${id}-err`].filter(Boolean).join(' ') || undefined;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-ink-2">{label}</label>
      <div className="relative">
        <input ref={ref} id={id} type={revealable && shown ? 'text' : type} aria-invalid={!!error} aria-describedby={describedBy}
          {...rest}
          className={cx('h-9 w-full rounded border bg-white px-2.5 text-sm placeholder:text-mute/70 hover:border-[#8996a5] focus:border-primary focus:outline-none focus:shadow-ring disabled:bg-surface2 disabled:text-mute',
            error ? 'border-danger' : 'border-strong', revealable && 'pr-9', className)} />
        {revealable && (
          <button type="button" onClick={() => setShown((v) => !v)} aria-pressed={shown} aria-label={shown ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
            title={shown ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'} tabIndex={-1}
            className="absolute right-1 top-1 grid size-7 place-items-center rounded text-mute hover:bg-surface2 hover:text-ink">
            <Icon name={shown ? 'eyeOff' : 'eye'} size={16} />
          </button>
        )}
      </div>
      {error ? <p id={`${id}-err`} role="alert" className="text-xs text-danger">{error}</p>
        : hint ? <p id={`${id}-hint`} className="text-xs text-mute">{hint}</p> : null}
    </div>
  );
});
