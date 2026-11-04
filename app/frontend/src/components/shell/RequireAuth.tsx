import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../auth/AuthProvider';
import { ForcedPasswordPage } from '../../features/auth/ForcedPasswordPage';
import { Spinner } from '../ui/primitives';
import { Shell } from './Shell';

/** The gate in front of the whole app: signed in, and not stuck on a temporary password. */
export function RequireAuth() {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status === 'loading') {
    return <div className="grid min-h-dvh place-items-center bg-app" role="status" aria-label="Đang tải"><Spinner className="size-6" /></div>;
  }
  if (state.status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  if (state.user.must_change_password) return <ForcedPasswordPage />;
  return <Shell />;
}
