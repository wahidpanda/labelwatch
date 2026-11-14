import { Link } from 'react-router'

import { API_BASE_URL } from '@/api/client'
import { useStale } from '@/api/queries'
import { QueryState } from '@/components/QueryState'
import { formatDate, useDocumentTitle } from '@/lib/format'

export function StalePage() {
  useDocumentTitle('Not yet reflected')
  const stale = useStale()

  return (
    <section aria-labelledby="stale-title" className="space-y-6">
      <header className="space-y-2">
        <h1 id="stale-title" className="text-3xl font-semibold">
          Not yet reflected
        </h1>
        <p className="max-w-prose text-muted-foreground">
          Generic labels whose current published version does not yet show a brand safety change
          made more than the stale threshold ago. A change may be pending at FDA or worded
          differently.
        </p>
        <a
          href={`${API_BASE_URL}/api/v1/generics/stale?format=csv`}
          download="stale_generics.csv"
          className="inline-block text-sm underline"
        >
          Download CSV
        </a>
      </header>
      <QueryState query={stale} label="stale generics">
        {(page) =>
          page.items.length === 0 ? (
            <p className="text-muted-foreground">Nothing is past the threshold.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left">
                  <tr>
                    <th scope="col" className="px-4 py-2">Generic label</th>
                    <th scope="col" className="px-4 py-2">Brand change</th>
                    <th scope="col" className="px-4 py-2 text-right">Days since change</th>
                    <th scope="col" className="px-4 py-2">Latest generic version</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((s) => (
                    <tr key={s.judgement_id} className="border-t align-top">
                      <th scope="row" className="px-4 py-2 text-left font-normal">
                        {s.generic_set.labeler ?? s.generic_set.title}
                      </th>
                      <td className="px-4 py-2">
                        <Link to={`/events/${s.event_id}#j-${s.judgement_id}`} className="hover:underline">
                          {s.claim_text}
                        </Link>
                        <span className="block text-xs text-muted-foreground">
                          {formatDate(s.event_date)}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {s.days_since_event.toLocaleString('en-US')}
                      </td>
                      <td className="px-4 py-2">{formatDate(s.latest_version_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </QueryState>
    </section>
  )
}
