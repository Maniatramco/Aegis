type Session = { userId?: string; csrf: string };

// Only retry the explicit authentication-layer rejection, which precedes the
// endpoint's mutations. Network failures and other 403s must never be replayed.
export async function fetchWithSessionCsrf(
  url: string,
  init: RequestInit,
  session: Session,
  updateToken: (token: string) => void,
  transport: typeof fetch = fetch,
): Promise<Response> {
  const response = await transport(url, init);
  if (['GET', 'HEAD', 'OPTIONS'].includes((init.method || 'GET').toUpperCase()) || response.status !== 403 || !session.userId) return response;
  let detail;
  try { detail = (await response.clone().json()).detail; } catch { return response; }
  if (detail !== 'Invalid CSRF token') return response;

  const current = await transport('/api/auth/me', { credentials: 'include', cache: 'no-store', signal: init.signal });
  if (current.status === 401) throw Object.assign(new Error('Your session expired. Sign in again to continue.'), { status: 401 });
  if (!current.ok) return response;
  const data = await current.json();
  if (data.user?.id !== session.userId) throw new Error('Your signed-in account changed. Reload the page before continuing.');
  if (typeof data.csrf_token !== 'string' || !data.csrf_token) return response;
  updateToken(data.csrf_token);
  const headers = new Headers(init.headers);
  headers.set('X-CSRF-Token', data.csrf_token);
  return transport(url, { ...init, headers });
}
