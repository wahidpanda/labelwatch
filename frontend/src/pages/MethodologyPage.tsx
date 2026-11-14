import { useMethodology } from '@/api/queries'
import { MethodologyFlow } from '@/components/MethodologyFlow'
import { QueryState } from '@/components/QueryState'
import { useDocumentTitle } from '@/lib/format'

const STEPS = [
  'Brand and generic labels are matched through the FDA Orange Book reference listing.',
  'Every published version of each label is downloaded from DailyMed; safety sections are kept.',
  'Consecutive brand versions are compared unit by unit. A language model sorts each added or changed unit into a substantive safety change or an editorial edit.',
  'For each change, the matching generic sections are searched. Near-identical text counts as reflected; clearly unrelated text counts as not reflected; otherwise a model judges, and its quotes must appear word for word in the generic label.',
  'The lag is the time from the brand version that introduced the change to the first generic version that reflects it.',
]

export function MethodologyPage() {
  useDocumentTitle('Methodology')
  const methodology = useMethodology()
  return (
    <article className="max-w-prose space-y-8" aria-labelledby="method-title">
      <h1 id="method-title" className="text-3xl font-semibold">
        Methodology
      </h1>
      <MethodologyFlow />
      <section aria-labelledby="steps-title" className="space-y-3">
        <h2 id="steps-title" className="text-xl font-semibold">
          How it works
        </h2>
        <ol className="list-decimal space-y-2 pl-5">
          {STEPS.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      </section>
      <QueryState query={methodology} label="methodology">
        {(m) => (
          <>
            <section aria-labelledby="limits-title" className="space-y-3">
              <h2 id="limits-title" className="text-xl font-semibold">
                Known limits
              </h2>
              <ul className="list-disc space-y-2 pl-5">
                {m.limits.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </section>
            <p className="rounded-lg bg-muted/40 p-4 text-sm">{m.disclaimer}</p>
            <p className="text-sm text-muted-foreground">
              Prompt version {m.prompt_version}. Stale threshold {m.stale_days} days.
            </p>
          </>
        )}
      </QueryState>
    </article>
  )
}
