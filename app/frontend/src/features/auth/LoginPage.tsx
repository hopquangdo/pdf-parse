import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { Icon } from '../../components/ui/Icon';
import { TextField } from '../../components/ui/TextField';
import { Button } from '../../components/ui/primitives';
import { AuthLayout } from './AuthLayout';

const EMAIL_SHAPE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function LoginPage() {
  const { state, login } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const email = useRef<HTMLInputElement>(null);
  const password = useRef<HTMLInputElement>(null);
  const [emailValue, setEmailValue] = useState('');
  const [passwordValue, setPasswordValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<{ email?: string; password?: string }>({});

  const refocusPassword = useRef(false);

  useEffect(() => email.current?.focus(), []);
  // The field is disabled while the request runs, so focus can only return once it is enabled again.
  useEffect(() => {
    if (!busy && refocusPassword.current) {
      refocusPassword.current = false;
      password.current?.focus();
    }
  }, [busy]);

  if (state.status === 'authenticated') return <Navigate to={from && from !== '/login' ? from : '/'} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const errors: typeof fieldError = {};
    if (!EMAIL_SHAPE.test(emailValue.trim())) errors.email = 'Nhập địa chỉ email.';
    if (!passwordValue) errors.password = 'Nhập mật khẩu.';
    setFieldError(errors);
    if (errors.email) return email.current?.focus();
    if (errors.password) return password.current?.focus();
    setBusy(true);
    setProblem(null);
    try {
      await login(emailValue.trim(), passwordValue);
      navigate(from && from !== '/login' ? from : '/', { replace: true });
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : 'Có lỗi xảy ra. Hãy thử lại.');
      setPasswordValue('');
      refocusPassword.current = true;
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Đăng nhập" subtitle="Dùng tài khoản do quản trị viên cấp cho bạn."
      footer="Không đăng nhập được? Nhờ quản trị viên đặt lại mật khẩu.">
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        {problem && (
          <div role="alert" className="flex items-start gap-2 rounded border border-danger-line bg-danger-soft px-3 py-2 text-sm text-danger">
            <span className="mt-0.5"><Icon name="alert" size={16} /></span>
            <span>{problem}</span>
          </div>
        )}
        <TextField ref={email} label="Email" type="email" name="email" autoComplete="username" inputMode="email" autoCapitalize="none"
          spellCheck={false} value={emailValue} disabled={busy} error={fieldError.email}
          onChange={(e) => { setEmailValue(e.target.value); setFieldError((f) => ({ ...f, email: undefined })); }} />
        <TextField ref={password} label="Mật khẩu" name="password" autoComplete="current-password" revealable value={passwordValue}
          type="password" disabled={busy} error={fieldError.password}
          onChange={(e) => { setPasswordValue(e.target.value); setFieldError((f) => ({ ...f, password: undefined })); }} />
        <Button type="submit" variant="primary" loading={busy} className="h-10 w-full">
          {busy ? 'Đang đăng nhập…' : 'Đăng nhập'}
        </Button>
      </form>
    </AuthLayout>
  );
}
