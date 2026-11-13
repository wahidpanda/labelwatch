import { NavLink, Outlet } from 'react-router'

export function Layout() {
  return (
    <div className="flex min-h-svh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <NavLink to="/" className="font-serif text-xl font-semibold">
            Label Lag Radar
          </NavLink>
          <nav aria-label="Main">
            <ul className="flex gap-6 text-sm">
              <li>
                <NavLink to="/" end className="hover:underline">
                  Dashboard
                </NavLink>
              </li>
            </ul>
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-6 py-10">
        <Outlet />
      </main>

      <footer className="border-t border-line text-sm text-ink-muted">
        <div className="mx-auto max-w-6xl space-y-1 px-6 py-6">
          <p>Not medical advice. Not a regulatory finding.</p>
          <p>
            Dates are DailyMed publication dates, not FDA approval dates. DailyMed holds
            company-submitted labeling; a change may be pending at FDA or implemented under
            different wording.
          </p>
        </div>
      </footer>
    </div>
  )
}
