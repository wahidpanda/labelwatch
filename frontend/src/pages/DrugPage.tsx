import { Link, useParams } from 'react-router'

import type { DrugMatrix } from '@/api/client'
import { useDrug, useDrugMatrix } from '@/api/queries'
import { QueryState } from '@/components/QueryState'
import { StatusBadge } from '@/components/StatusBadge'
import { formatDate, formatDays, sectionName, title, useDocumentTitle } from '@/lib/format'
import { STATUS_LABEL } from '@/lib/status'

const CELL: Record<string, string> = {
  propagated: 'bg-emerald-500',
  partial: 'bg-amber-400',
  not_propagated: 'bg-rose-500',
  insufficient_evidence: 'bg-muted-foreground/40',
}
const SYMBOL: Record<string, string> = {
  propagated: '✓',
  partial: '~',
  not_propagated: '✕',
  insufficient_evidence: '?',
}

function Heatmap({ matrix }: { matrix: DrugMatrix }) {
  if (matrix.events.length === 0) {
    return <p className="text-muted-foreground">No brand safety events detected yet.</p>
  }
  const events = [...matrix.events].reverse()
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="text-xs">
        <caption className="sr-only">
          Status of each brand safety event (columns) in each generic label (rows)
        </caption>
        <thead>
          <tr>
            <th scope="col" className="sticky left-0 bg-background px-3 py-2 text-left">
              Generic label
            </th>
            {events.map((e, i) => (
              <th key={e.id} scope="col" className="px-1 py-2 font-normal">
                <Link
                  to={`/events/${e.id}`}
                  title={`${formatDate(e.event_date)}: ${e.claim_text}`}
                  className="underline-offset-2 hover:underline"
                >
                  E{i + 1}
                </Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.rows.map((row) => (
            <tr key={row.generic_set.setid} className="border-t">
              <th
                scope="row"
                className="sticky left-0 max-w-64 truncate bg-background px-3 py-1 text-left font-normal"
                title={row.generic_set.title}
              >
                {row.generic_set.labeler ?? row.generic_set.title}
              </th>
              {events.map((e) => {
                const cell = row.cells[e.id]
                if (!cell) {
                  return (
                    <td key={e.id} className="px-1 py-1 text-center text-muted-foreground">
                      <span aria-label="Not judged">·</span>
                    </td>
                  )
                }
                const label = `${STATUS_LABEL[cell.status]}${cell.lag_days !== null ? `, ${formatDays(cell.lag_days)}` : ''}`
                return (
                  <td key={e.id} className="px-1 py-1 text-center">
                    <Link
                      to={`/events/${e.id}#j-${cell.judgement_id}`}
                      aria-label={label}
                      title={label}
                      className={`inline-flex size-6 items-center justify-center rounded text-white ${CELL[cell.status] ?? ''}`}
                    >
                      {SYMBOL[cell.status]}
                    </Link>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DrugPage() {
  const { drugId = '' } = useParams()
  const drug = useDrug(drugId)
  const matrix = useDrugMatrix(drugId)
  useDocumentTitle(drug.data ? title(drug.data.ingredient) : 'Drug')

  return (
    <QueryState query={drug} label="drug">
      {(d) => (
        <article className="space-y-10" aria-labelledby="drug-title">
          <header className="space-y-2">
            <p className="text-sm text-muted-foreground">
              <Link to="/" className="hover:underline">
                Dashboard
              </Link>{' '}
              / Drug
            </p>
            <h1 id="drug-title" className="text-3xl font-semibold">
              {title(d.ingredient)}
            </h1>
            <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
              <div>
                <dt className="text-muted-foreground">Events</dt>
                <dd className="text-lg font-semibold tabular-nums">{d.events}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Generic labels</dt>
                <dd className="text-lg font-semibold tabular-nums">{d.generics}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Median lag</dt>
                <dd className="text-lg font-semibold tabular-nums">{formatDays(d.median_lag_days)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">90th percentile lag</dt>
                <dd className="text-lg font-semibold tabular-nums">{formatDays(d.p90_lag_days)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Not yet reflected</dt>
                <dd className="text-lg font-semibold tabular-nums">{d.stale_generics}</dd>
              </div>
            </dl>
          </header>

          <section aria-labelledby="heatmap-title" className="space-y-3">
            <h2 id="heatmap-title" className="text-xl font-semibold">
              Generic labels by event
            </h2>
            <ul className="flex flex-wrap gap-3" aria-label="Legend">
              {(['propagated', 'partial', 'not_propagated', 'insufficient_evidence'] as const).map(
                (s) => (
                  <li key={s}>
                    <StatusBadge status={s} />
                  </li>
                ),
              )}
            </ul>
            <QueryState query={matrix} label="heatmap">
              {(m) => <Heatmap matrix={m} />}
            </QueryState>
          </section>

          <section aria-labelledby="events-title" className="space-y-3">
            <h2 id="events-title" className="text-xl font-semibold">
              Brand safety events
            </h2>
            <QueryState query={matrix} label="events">
              {(m) => (
                <ol className="space-y-3">
                  {m.events.map((e) => (
                    <li key={e.id} className="rounded-lg border p-4">
                      <p className="text-xs text-muted-foreground">
                        {formatDate(e.event_date)} · {sectionName(e.section_key)} · {e.severity}
                      </p>
                      <Link to={`/events/${e.id}`} className="font-medium hover:underline">
                        {e.claim_text}
                      </Link>
                    </li>
                  ))}
                </ol>
              )}
            </QueryState>
          </section>
        </article>
      )}
    </QueryState>
  )
}
