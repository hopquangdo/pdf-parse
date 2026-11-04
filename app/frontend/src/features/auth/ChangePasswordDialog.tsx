import { useEffect } from 'react';
import { Dialog, useToast } from '../../components/ui/feedback';
import { Button } from '../../components/ui/primitives';
import { useChangePassword } from './useChangePassword';

export function ChangePasswordDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const { fields, submit, busy, reset } = useChangePassword(() => {
    toast('Đã đổi mật khẩu. Các thiết bị khác đã bị đăng xuất.', { kind: 'success' });
    onClose();
  });
  useEffect(() => { if (!open) reset(); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps -- reset is stable enough; run only on close
  return (
    <Dialog open={open} title="Đổi mật khẩu" onClose={onClose} onSubmit={() => void submit()}
      actions={<>
        <Button onClick={onClose} disabled={busy}>Hủy</Button>
        <Button type="submit" variant="primary" loading={busy}>Lưu mật khẩu</Button>
      </>}>
      {fields}
    </Dialog>
  );
}
