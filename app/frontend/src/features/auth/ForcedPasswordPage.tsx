import type { FormEvent } from 'react';
import { useAuth } from '../../auth/AuthProvider';
import { useToast } from '../../components/ui/feedback';
import { Button } from '../../components/ui/primitives';
import { AuthLayout } from './AuthLayout';
import { useChangePassword } from './useChangePassword';

/** Shown instead of the app while the account still carries a temporary password. */
export function ForcedPasswordPage() {
  const { logout } = useAuth();
  const toast = useToast();
  const { fields, submit, busy } = useChangePassword(() => toast('Đã đổi mật khẩu', { kind: 'success' }));
  const onSubmit = (e: FormEvent) => { e.preventDefault(); void submit(); };
  return (
    <AuthLayout title="Đặt mật khẩu mới" subtitle="Bạn đang dùng mật khẩu tạm. Hãy đặt mật khẩu riêng để tiếp tục."
      footer={<button type="button" onClick={() => void logout()} className="text-primary hover:underline">Đăng xuất</button>}>
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {fields}
        <Button type="submit" variant="primary" loading={busy} className="h-10 w-full">{busy ? 'Đang lưu…' : 'Lưu mật khẩu'}</Button>
      </form>
    </AuthLayout>
  );
}
