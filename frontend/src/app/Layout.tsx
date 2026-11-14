import { Activity, BookOpen, Flag, LayoutDashboard, LogOut, Pill, Sparkles } from 'lucide-react'
import { NavLink, Outlet } from 'react-router'

import { ChatDock } from '@/components/ChatDock'
import { authRequired, clearAuth } from '@/lib/auth'

const nav = [
  { to: '/', end: true, label: 'Dashboard', icon: LayoutDashboard },
  { to: '/stale', label: 'Not yet reflected', icon: Flag },
  { to: '/leaflet', label: 'Leaflet check', icon: BookOpen },
  { to: '/bd', label: 'BD brands', icon: Pill },
  { to: '/methodology', label: 'Methodology', icon: Sparkles },
  { to: '/ops/llm', label: 'LLM & traces', icon: Activity },
] as const

export function Layout() {
  return (
    <div className="relative flex min-h-svh flex-col">
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(ellipse_80%_50%_at_50%_-10%,oklch(0.88_0.06_230/0.35),transparent),radial-gradient(ellipse_60%_40%_at_100%_0%,oklch(0.92_0.04_180/0.25),transparent)]"
      />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <NavLink to="/" className="font-heading text-lg font-semibold tracking-tight sm:text-xl">
            Label Lag Radar
          </NavLink>
          <nav aria-label="Main" className="max-w-full overflow-x-auto">
            <ul className="flex gap-1 sm:gap-2">
              {nav.map((item) => (
                <li key={item.to} className="shrink-0">
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted/80 hover:text-foreground aria-[current=page]:bg-primary aria-[current=page]:text-primary-foreground sm:text-sm"
                  >
                    <item.icon className="size-3.5 opacity-80 sm:size-4" aria-hidden />
                    <span className="whitespace-nowrap">{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          {authRequired && (
            <button
              type="button"
              className="flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted sm:text-sm"
              onClick={() => {
                clearAuth()
                window.location.href = '/'
              }}
            >
              <LogOut className="size-3.5" aria-hidden />
              Sign out
            </button>
          )}
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
        <Outlet />
      </main>

      <ChatDock />

      <footer className="border-t border-border/60 text-sm text-muted-foreground">
        <div className="mx-auto max-w-6xl space-y-1 px-4 py-6 sm:px-6">
          <p>Not medical advice. Not a regulatory finding.</p>
          <p className="max-w-prose text-xs sm:text-sm">
            Dates are DailyMed publication dates, not FDA approval dates.
          </p>
        </div>
      </footer>
    </div>
  )
}
