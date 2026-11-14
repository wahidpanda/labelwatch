import { Link, useParams } from 'react-router'

import type { JudgementOut } from '@/api/client'
import { useEvent, useEventJudgements } from '@/api/queries'
import { QueryState } from '@/components/QueryState'
import { StatusBadge } from '@/components/StatusBadge'
import { formatDate, formatDays, sectionName, title, useDocumentTitle } from '@/lib/format'

const METHOD_LABEL: Record<string, string> = {
  baseline_exact: 'Same text found',
  baseline_lexical: 'No similar text found',
  baseline_unchanged: 'Section unchanged',
  llm: 'Model judgement with verified quotes',
  human: 'Reviewed by a person',
}

function dailyMedUrl(setid: string) {
  return `https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=${setid}`
}

function Judgement({ j }: { j: JudgementOut }) {
  const quotes = Array.isArray(j.evidence.quotes) ? (j.evidence.quotes as string[]) : []
  return (
    <li id={`j-${j.id}`} className="space-y-2 rounded-lg border p-4 target:ring-2 target:ring-ring">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <a
          href={dailyMedUrl(j.generic_set.setid)}
          target="_blank"
          rel="noreferrer"
          className="font-medium hover:underline"
        >
          {j.generic_set.labeler ?? j.generic_set.title}
          <span className="sr-only"> (opens DailyMed in a new tab)</span>
        </a>
        <StatusBadge status={j.status} />
      </div>
      <p className="text-sm text-muted-foreground">
        {j.first_version
          ? `First reflected in version ${j.first_version.number} (${formatDate(j.first_version.date)}), lag ${formatDays(j.lag_days)}.`
          : 'No published version reflects this change yet.'}{' '}
        {METHOD_LABEL[j.method] ?? j.method}
        {j.confidence !== null ? `, confidence ${Math.round(j.confidence * 100)}%` : ''}.
        {j.non_monotonic ? ' An earlier version carried the text and a later one dropped it.' : ''}
      </p>
      {quotes.length > 0 && (
        <figure className="space-y-1">
          <figcaption className="text-xs text-muted-foreground">Generic label text</figcaption>
          {quotes.map((q) => (
            <blockquote key={q} className="border-l-2 pl-3 text-sm">
              {q}
            </blockquote>
          ))}
        </figure>
      )}
    </li>
  )
}

export function EventPage() {
  const { eventId = '' } = useParams()
  const event = useEvent(eventId)
  const judgements = useEventJudgements(eventId)
  useDocumentTitle('Safety event')

  return (
    <QueryState query={event} label="event">
      {(e) => (
        <article className="space-y-8" aria-labelledby="event-title">
          <header className="space-y-3">
            <p className="text-sm text-muted-foreground">
              <Link to="/" className="hover:underline">
                Dashboard
              </Link>{' '}
              /{' '}
              <Link to={`/drugs/${e.drug_id}`} className="hover:underline">
                {title(e.ingredient)}
              </Link>{' '}
              / Event
            </p>
            <h1 id="event-title" className="text-2xl font-semibold">
              {e.claim_text}
            </h1>
            <p className="text-sm text-muted-foreground">
              {formatDate(e.event_date)} · {sectionName(e.section_key)} · {e.change_type} ·{' '}
              {e.severity}
            </p>
            <figure className="space-y-1 rounded-lg bg-muted/40 p-4">
              <figcaption className="text-xs text-muted-foreground">
                Brand label text, version {e.brand_version} of{' '}
                <a href={dailyMedUrl(e.brand_setid)} target="_blank" rel="noreferrer" className="underline">
                  {e.brand_title}
                </a>
              </figcaption>
              <blockquote className="text-sm">{e.brand_unit}</blockquote>
            </figure>
            <dl className="flex flex-wrap gap-4 text-sm">
              {(
                [
                  ['propagated', e.counts.propagated],
                  ['partial', e.counts.partial],
                  ['not_propagated', e.counts.not_propagated],
                  ['insufficient_evidence', e.counts.insufficient_evidence],
                ] as const
              ).map(([status, count]) => (
                <div key={status} className="flex items-center gap-2">
                  <dt>
                    <StatusBadge status={status} />
                  </dt>
                  <dd className="tabular-nums">{count}</dd>
                </div>
              ))}
            </dl>
          </header>

          <section aria-labelledby="judgements-title" className="space-y-3">
            <h2 id="judgements-title" className="text-xl font-semibold">
              Generic labels
            </h2>
            <QueryState query={judgements} label="judgements">
              {(page) =>
                page.items.length === 0 ? (
                  <p className="text-muted-foreground">No generic labels judged yet.</p>
                ) : (
                  <ul className="space-y-3">
                    {page.items.map((j) => (
                      <Judgement key={j.id} j={j} />
                    ))}
                  </ul>
                )
              }
            </QueryState>
          </section>
        </article>
      )}
    </QueryState>
  )
}
