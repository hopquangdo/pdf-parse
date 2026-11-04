import { useState, type ReactNode } from 'react';
import { ApiError } from '../../api/client';
import { useAuth, useUser } from '../../auth/AuthProvider';
import { TextField } from '../../components/ui/TextField';
import { passwordProblem } from '../../lib/password';

/** State and fields of the change-password form, shared by the forced full page and the voluntary dialog. */
export function useChangePassword(onDone: () => void): { fields: ReactNode; submit: () => Promise<void>; busy: boolean; reset: () => void } {
  const { changePassword } = useAuth();
  const user = useUser();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<{ current?: string; next?: string; again?: string; form?: string }>({});

  const reset = () => { setCurrent(''); setNext(''); setAgain(''); setErrors({}); setBusy(false); };

  const submit = async () => {
    if (busy) return;
    const e: typeof errors = {};
    if (!current) e.current = 'Nhập mật khẩu hiện tại.';
    const weak = passwordProblem(next, user.email);
    if (weak) e.next = weak;
    else if (next === current) e.next = 'Hãy chọn mật khẩu khác mật khẩu hiện tại.';
    if (!e.next && again !== next) e.again = 'Hai mật khẩu không khớp.';
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    try {
      await changePassword(current, next);
      reset();
      onDone();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Có lỗi xảy ra. Hãy thử lại.';
      // 400 means the current password was wrong; anything else is about the new password or the request.
      setErrors(err instanceof ApiError && err.status === 400 ? { current: msg } : err instanceof ApiError && err.code === 'weak_password' ? { next: msg } : { form: msg });
      setBusy(false);
    }
  };

  const fields = (
    <div className="flex flex-col gap-3.5">
      {errors.form && <p role="alert" className="rounded border border-danger-line bg-danger-soft px-3 py-2 text-sm text-danger">{errors.form}</p>}
      <TextField label="Mật khẩu hiện tại" type="password" revealable autoComplete="current-password" value={current} disabled={busy}
        error={errors.current} onChange={(e) => setCurrent(e.target.value)} />
      <TextField label="Mật khẩu mới" type="password" revealable autoComplete="new-password" value={next} disabled={busy}
        hint="Ít nhất 10 ký tự. Ghép vài từ ngẫu nhiên là một cách tốt." error={errors.next} onChange={(e) => setNext(e.target.value)} />
      <TextField label="Nhập lại mật khẩu mới" type="password" revealable autoComplete="new-password" value={again} disabled={busy}
        error={errors.again} onChange={(e) => setAgain(e.target.value)} />
    </div>
  );
  return { fields, submit, busy, reset };
}
