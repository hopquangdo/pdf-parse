import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { cx } from '../../lib/cx';
import { Button } from './primitives';

/* ---------------- toasts ---------------- */
interface ToastOptions {
  kind?: 'info' | 'success' | 'error';
  action?: { label: string; onClick: () => void };
  duration?: number;
}
interface ToastItem extends ToastOptions { id: number; message: string }
type ToastFn = (message: string, options?: ToastOptions) => void;

const ToastContext = createContext<ToastFn>(() => undefined);
export const useToast = () => useContext(ToastContext);

const TOAST_EDGE = { info: 'border-l-[#8fb4dd]', success: 'border-l-[#56d364]', error: 'border-l-[#ff7b72]' };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(0);
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const toast = useCallback<ToastFn>((message, options = {}) => {
    const id = next.current++;
    setItems((xs) => [...xs, { id, message, ...options }]);
    setTimeout(() => dismiss(id), options.duration ?? (options.kind === 'error' ? 7000 : 4000));
  }, [dismiss]);
  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div aria-live="polite" className="toasts fixed bottom-5 right-5 z-50 flex max-w-[min(440px,calc(100vw-32px))] flex-col gap-1.5">
        {items.map((t) => (
          <div key={t.id} role={t.kind === 'error' ? 'alert' : 'status'}
            className={cx('toast flex animate-pop items-center gap-3 border-l-4 bg-ink px-3 py-2 text-white shadow-pop', TOAST_EDGE[t.kind ?? 'info'])}>
            <span className="flex-1">{t.message}</span>
            {t.action && (
              <button type="button" className="cursor-pointer px-1 text-2xs font-medium uppercase tracking-wider underline focus-visible:outline-white"
                onClick={() => { t.action?.onClick(); dismiss(t.id); }}>
                {t.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/* ---------------- dialogs (native <dialog>: focus trap, Esc and inert background come from the platform) ---------------- */
export function Dialog({ open, title, onClose, onSubmit, children, actions }: {
  open: boolean;
  title: string;
  onClose: () => void;
  /** Makes the dialog a form: Enter and any type="submit" button in `actions` call this. */
  onSubmit?: () => void;
  children?: ReactNode;
  actions: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useMemo(() => `dlg-${Math.random().toString(36).slice(2)}`, []);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);
  return (
    <dialog ref={ref} aria-labelledby={titleId} onClose={onClose} onClick={(e) => { if (e.target === ref.current) onClose(); }}
      className="w-[min(460px,calc(100vw-32px))] rounded-lg border border-strong bg-white p-0 text-ink shadow-modal">
      {open && (
        <form method="dialog" onSubmit={(e) => { e.preventDefault(); onSubmit?.(); }} className="flex flex-col">
          <h3 id={titleId} className="border-b border-strong bg-chrome px-4 py-2.5 text-2xs font-medium uppercase tracking-[.08em]">{title}</h3>
          <div className="p-4 text-ink-2">{children}</div>
          <div className="flex justify-end gap-1.5 border-t border-line bg-surface px-4 py-2.5">{actions}</div>
        </form>
      )}
    </dialog>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'Xác nhận', cancelLabel = 'Hủy', danger, onConfirm, onCancel }: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog open={open} title={title} onClose={onCancel}
      actions={<>
        <Button onClick={onCancel}>{cancelLabel}</Button>
        <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} autoFocus>{confirmLabel}</Button>
      </>}>
      {message}
    </Dialog>
  );
}
