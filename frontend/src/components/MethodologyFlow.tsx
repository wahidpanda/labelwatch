import { useEffect, useState } from 'react'

const STEPS = [
  { id: 'ob', title: 'Orange Book', detail: 'Links each generic to its brand (RLD).' },
  { id: 'dm', title: 'DailyMed', detail: 'Downloads every published label version.' },
  { id: 'ingest', title: 'Ingest', detail: 'Stores versions and safety sections by LOINC.' },
  { id: 'detect', title: 'Detect', detail: 'Diffs brand versions; keeps substantive safety changes.' },
  { id: 'judge', title: 'Judge', detail: 'Checks each generic label; quotes must match word for word.' },
  { id: 'lag', title: 'Lag', detail: 'Days from brand change to first reflecting generic version.' },
  { id: 'you', title: 'You', detail: 'Dashboard, heatmap, leaflet check (BD), and chat overview.' },
] as const

export function MethodologyFlow() {
  const [active, setActive] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActive((n) => (n + 1) % STEPS.length)
    }, 2800)
    return () => {
      window.clearInterval(timer)
    }
  }, [])

  const current = STEPS[active] ?? STEPS[0]

  return (
    <section
      aria-labelledby="flow-title"
      className="max-w-3xl space-y-4 rounded-lg border bg-muted/20 p-4"
    >
      <h2 id="flow-title" className="text-xl font-semibold">
        Animated pipeline
      </h2>
      <p className="text-sm text-muted-foreground">
        Highlights one step every few seconds. Dates are DailyMed publication dates, not FDA approval
        dates. Not medical advice.
      </p>
      <ol className="flex flex-wrap items-center gap-2" aria-label="Pipeline steps">
        {STEPS.map((step, index) => {
          const isActive = index === active
          return (
            <li key={step.id} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setActive(index)
                }}
                className={`rounded-md border px-3 py-2 text-left text-sm transition-all duration-500 ${
                  isActive
                    ? 'scale-105 border-primary bg-primary/10 font-semibold shadow-sm ring-2 ring-primary/40'
                    : 'opacity-70 hover:opacity-100'
                }`}
                aria-current={isActive ? 'step' : undefined}
              >
                <span className="block text-xs text-muted-foreground">Step {index + 1}</span>
                {step.title}
              </button>
              {index < STEPS.length - 1 && (
                <span className="hidden text-muted-foreground sm:inline" aria-hidden="true">
                  →
                </span>
              )}
            </li>
          )
        })}
      </ol>
      <p
        key={current.id}
        className="min-h-[3rem] text-sm transition-opacity duration-500"
        role="status"
        aria-live="polite"
      >
        <strong>{current.title}:</strong> {current.detail}
      </p>
      <div className="relative h-2 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-primary transition-all duration-700 ease-in-out"
          style={{ width: `${((active + 1) / STEPS.length) * 100}%` }}
          aria-hidden="true"
        />
      </div>
    </section>
  )
}
