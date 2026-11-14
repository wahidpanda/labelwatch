import { type ReactNode, useState } from 'react'

import { authRequired, isLoggedIn, saveAuth, verifyLogin } from '@/lib/auth'

export function AuthGate({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [ok, setOk] = useState(isLoggedIn())

  if (!authRequired || ok) return children

  return (
    <div className="grid min-h-svh place-items-center bg-[radial-gradient(ellipse_at_top,oklch(0.95_0.03_230),oklch(0.99_0_0))] px-6">
      <form
        className="w-full max-w-sm space-y-4 rounded-2xl border bg-card/90 p-6 shadow-xl backdrop-blur"
        onSubmit={(e) => {
          e.preventDefault()
          void (async () => {
            if (!username.trim() || !password) {
              setError('Enter username and password.')
              return
            }
            setBusy(true)
            setError('')
            const valid = await verifyLogin(username.trim(), password)
            setBusy(false)
            if (!valid) {
              setError('Invalid username or password.')
              return
            }
            saveAuth(username.trim(), password)
            setOk(true)
          })()
        }}
      >
        <h1 className="text-xl font-semibold">Label Lag Radar</h1>
        <p className="text-sm text-muted-foreground">Sign in to view label lag data and LLM ops.</p>
        <label className="block text-sm">
          Username
          <input
            className="mt-1 w-full rounded-lg border px-3 py-2"
            autoComplete="username"
            value={username}
            onChange={(e) => {
              setUsername(e.target.value)
            }}
          />
        </label>
        <label className="block text-sm">
          Password
          <input
            type="password"
            className="mt-1 w-full rounded-lg border px-3 py-2"
            autoComplete="current-password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
            }}
          />
        </label>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-primary py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
        >
          {busy ? 'Checking…' : 'Continue'}
        </button>
      </form>
    </div>
  )
}
