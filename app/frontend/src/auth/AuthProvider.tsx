import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, refreshSession } from '../api/client';
import type { AuthUser } from '../api/types';
import { session } from './session';

type State = { status: 'loading' } | { status: 'anonymous' } | { status: 'authenticated'; user: AuthUser };

interface AuthApi {
  state: State;
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
}

const AuthContext = createContext<AuthApi | null>(null);

export function useAuth(): AuthApi {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

/** The signed-in user. Only call it below the RequireAuth gate, where a user is guaranteed. */
export function useUser(): AuthUser {
  const { state } = useAuth();
  if (state.status !== 'authenticated') throw new Error('useUser called while signed out');
  return state.user;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [state, setState] = useState<State>({ status: 'loading' });

  // After a page load there is no access token in memory: the refresh cookie, if still valid, restores the session.
  useEffect(() => {
    let live = true;
    void refreshSession().then((body) => {
      if (live) setState(body ? { status: 'authenticated', user: body.user } : { status: 'anonymous' });
    });
    return () => { live = false; };
  }, []);

  const signedOut = useCallback(() => {
    qc.clear(); // nothing from the previous account may linger in the cache
    setState({ status: 'anonymous' });
  }, [qc]);

  // A request somewhere failed to refresh: the session is over (expired, revoked, or the account was disabled).
  useEffect(() => session.onExpired(signedOut), [signedOut]);

  const login = useCallback(async (email: string, password: string) => {
    const body = await api.login(email, password);
    qc.clear();
    setState({ status: 'authenticated', user: body.user });
    return body.user;
  }, [qc]);

  const logout = useCallback(async () => {
    await api.logout();
    signedOut();
  }, [signedOut]);

  const changePassword = useCallback(async (current: string, next: string) => {
    const { user } = await api.changePassword(current, next);
    setState({ status: 'authenticated', user });
  }, []);

  const value = useMemo(() => ({ state, login, logout, changePassword }), [state, login, logout, changePassword]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
