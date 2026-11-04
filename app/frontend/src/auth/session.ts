/**
 * The access token lives here, in memory only: never in localStorage, sessionStorage or a cookie, so it is not
 * readable by anything that can read storage, and it disappears when the tab closes. After a reload the page asks
 * /auth/refresh (which uses the HttpOnly refresh cookie) for a new one.
 */
type Listener = () => void;

let accessToken: string | null = null;
const expiredListeners = new Set<Listener>();

export const session = {
  get token(): string | null {
    return accessToken;
  },
  set(token: string | null): void {
    accessToken = token;
  },
  /** Called when the server says the session is over (refresh failed): the app must show the sign-in page. */
  onExpired(fn: Listener): () => void {
    expiredListeners.add(fn);
    return () => expiredListeners.delete(fn);
  },
  expire(): void {
    accessToken = null;
    expiredListeners.forEach((fn) => fn());
  },
};
