import { useEffect } from 'react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const KPIS = [
  { label: 'Drugs tracked', hint: 'Seed ingredients with a brand reference label' },
  { label: 'Safety events', hint: 'New or strengthened brand safety statements' },
  { label: 'Median lag (days)', hint: 'Between published brand and generic versions' },
  {
    label: 'Not yet reflected',
    hint: 'Share of generics whose published text does not yet show the change',
  },
  { label: 'Last ingestion', hint: 'Most recent DailyMed sync' },
] as const

export function DashboardPage() {
  useEffect(() => {
    document.title = 'Dashboard · Label Lag Radar'
  }, [])

  return (
    <section aria-labelledby="dashboard-title" className="space-y-8">
      <header className="space-y-2">
        <h1 id="dashboard-title" className="text-3xl font-semibold">
          Dashboard
        </h1>
        <p className="max-w-prose text-muted-foreground">
          How long generic labels take to reflect brand safety changes. Data appears here once
          ingestion has run.
        </p>
      </header>

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {KPIS.map((kpi) => (
          <li key={kpi.label}>
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="text-sm font-normal text-muted-foreground" title={kpi.hint}>
                  {kpi.label}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p
                  className="text-2xl font-semibold tabular-nums"
                  aria-label={`${kpi.label}: no data yet`}
                >
                  —
                </p>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  )
}
