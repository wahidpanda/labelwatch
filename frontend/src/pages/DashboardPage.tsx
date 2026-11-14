import { Link, useSearchParams } from 'react-router'

import { useDrugs, useOverview } from '@/api/queries'
import { QueryState } from '@/components/QueryState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDate, formatDays, formatPercent, title, useDocumentTitle } from '@/lib/format'

function Kpi({ label, hint, value }: { label: string; hint: string; value: string }) {
  return (
    <li>
      <Card className="h-full">
        <CardHeader>
          <CardTitle className="text-sm font-normal text-muted-foreground" title={hint}>
            {label}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-semibold tabular-nums" aria-label={`${label}: ${value}`}>
            {value}
          </p>
        </CardContent>
      </Card>
    </li>
  )
}

export function DashboardPage() {
  useDocumentTitle('Dashboard')
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const overview = useOverview()
  const drugs = useDrugs(q)

  return (
    <section aria-labelledby="dashboard-title" className="space-y-10">
      <header className="relative overflow-hidden rounded-2xl border bg-card/80 p-6 shadow-sm backdrop-blur sm:p-8">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-8 -top-8 size-40 rounded-full bg-primary/10 blur-2xl"
        />
        <h1 id="dashboard-title" className="text-3xl font-semibold">
          Label lag overview
        </h1>
        <p className="mt-2 max-w-prose text-muted-foreground">
          How long generic labels take to reflect brand safety changes, measured from published
          DailyMed label versions. Use the assistant button for quick questions.
        </p>
      </header>

      <QueryState query={overview} label="overview">
        {(o) => (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <Kpi label="Drugs tracked" hint="Seed ingredients" value={String(o.drugs)} />
            <Kpi
              label="Safety events"
              hint="New or strengthened brand safety statements"
              value={String(o.events)}
            />
            <Kpi
              label="Median lag"
              hint="Brand change to first generic version that reflects it"
              value={formatDays(o.median_lag_days)}
            />
            <Kpi
              label="Not yet reflected"
              hint="Share of current judgements older than the stale threshold"
              value={formatPercent(o.stale_share)}
            />
            <Kpi
              label="Last ingestion"
              hint="Most recent DailyMed sync"
              value={formatDate(o.last_ingestion_at)}
            />
          </ul>
        )}
      </QueryState>

      <section aria-labelledby="drugs-title" className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h2 id="drugs-title" className="text-xl font-semibold">
            Drugs
          </h2>
          <label className="flex flex-col gap-1 text-sm">
            Search ingredient
            <input
              type="search"
              value={q}
              onChange={(e) => {
                setParams(e.target.value ? { q: e.target.value } : {}, { replace: true })
              }}
              className="rounded-md border bg-background px-3 py-1.5"
            />
          </label>
        </div>
        <QueryState query={drugs} label="drugs">
          {(page) =>
            page.items.length === 0 ? (
              <p className="text-muted-foreground">No drugs match.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-left">
                    <tr>
                      <th scope="col" className="px-4 py-2">Ingredient</th>
                      <th scope="col" className="px-4 py-2 text-right">Events</th>
                      <th scope="col" className="px-4 py-2 text-right">Generics</th>
                      <th scope="col" className="px-4 py-2 text-right">Not yet reflected</th>
                      <th scope="col" className="px-4 py-2 text-right">Median lag</th>
                      <th scope="col" className="px-4 py-2">Latest event</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((d) => (
                      <tr key={d.id} className="border-t">
                        <th scope="row" className="px-4 py-2 text-left font-medium">
                          <Link to={`/drugs/${d.id}`} className="underline-offset-4 hover:underline">
                            {title(d.ingredient)}
                          </Link>
                        </th>
                        <td className="px-4 py-2 text-right tabular-nums">{d.events}</td>
                        <td className="px-4 py-2 text-right tabular-nums">{d.generics}</td>
                        <td className="px-4 py-2 text-right tabular-nums">{d.stale_generics}</td>
                        <td className="px-4 py-2 text-right tabular-nums">
                          {formatDays(d.median_lag_days)}
                        </td>
                        <td className="px-4 py-2">{formatDate(d.last_event_date)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </QueryState>
      </section>
    </section>
  )
}
