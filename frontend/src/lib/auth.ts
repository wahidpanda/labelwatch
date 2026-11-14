const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

const KEY = 'llr_basic_auth'

export const authRequired = import.meta.env.VITE_SITE_AUTH_REQUIRED === 'true'

function encodeBasic(username: string, password: string): string {
  const bytes = new TextEncoder().encode(`${username}:${password}`)
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary)
}

export function authHeader(): Record<string, string> {
  const token = sessionStorage.getItem(KEY)
  return token ? { Authorization: `Basic ${token}` } : {}
}

export function isLoggedIn(): boolean {
  return !authRequired || Boolean(sessionStorage.getItem(KEY))
}

export function saveAuth(username: string, password: string): void {
  sessionStorage.setItem(KEY, encodeBasic(username, password))
}

export function clearAuth(): void {
  sessionStorage.removeItem(KEY)
}

/** Confirms credentials against the API before storing them. */
export async function verifyLogin(username: string, password: string): Promise<boolean> {
  if (!authRequired) return true
  const res = await fetch(`${API_BASE_URL}/api/v1/stats/overview`, {
    headers: { Authorization: `Basic ${encodeBasic(username, password)}` },
  })
  return res.ok
}
