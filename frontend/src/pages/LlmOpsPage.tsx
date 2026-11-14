import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { API_BASE_URL } from '@/api/client'
import { formatDate, useDocumentTitle } from '@/lib/format'

type LlmOps = {
  as_of: string
  today: string
  traces_this_month: number
  langsmith_tracing: boolean
  langsmith_project: string
  langsmith_url: string | null
  cache_entries: number
  cache_by_task: Record<string, number>
  usage_today: {
    provider: string
    model: string
    calls: number
    tokens_in: number
    tokens_out: number
  }[]
  last_ingestion_at: string | null
}

async function fetchOps(): Promise<LlmOps> {
  const res = await fetch(`${API_BASE_URL}/api/v1/ops/llm`)
  if (!res.ok) throw new Error('Could not load LLM ops')
  return (await res.json()) as LlmOps
}

export function LlmOpsPage() {
  useDocumentTitle('LLM ops')
  const ops = useQuery({ queryKey: ['llm-ops'], queryFn: fetchOps, refetchInterval: 60_000 })

  return (
    <section className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold">LLM & tracing</h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          Daily provider usage, response cache, and LangSmith trace budget. Not medical advice.
        </p>
      </header>
      {ops.isError && <p className="text-sm text-destructive">Could not load ops.</p>}
      {ops.data && (
        <FadeIn className="grid gap-4 md:grid-cols-3">
          <StatCard label="Cache entries" value={String(ops.data.cache_entries)} />
          <StatCard label="Traces this month" value={String(ops.data.traces_this_month)} />
          <StatCard
            label="Last ingestion"
            value={ops.data.last_ingestion_at ? formatDate(ops.data.last_ingestion_at) : '—'}
          />
        </FadeIn>
      )}
      {ops.data && (
        <FadeIn delay className="overflow-x-auto rounded-xl border bg-card/50">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left">
              <tr>
                <th className="px-4 py-2">Provider</th>
                <th className="px-4 py-2">Model</th>
                <th className="px-4 py-2 text-right">Calls today</th>
                <th className="px-4 py-2 text-right">Tokens in</th>
                <th className="px-4 py-2 text-right">Tokens out</th>
              </tr>
            </thead>
            <tbody>
              {ops.data.usage_today.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-muted-foreground">
                    No LLM calls recorded today yet.
                  </td>
                </tr>
              ) : (
                ops.data.usage_today.map((u) => (
                  <tr key={`${u.provider}-${u.model}`} className="border-t">
                    <td className="px-4 py-2">{u.provider}</td>
                    <td className="px-4 py-2">{u.model}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{u.calls}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{u.tokens_in}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{u.tokens_out}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </FadeIn>
      )}
      {ops.data && (
        <div className="rounded-xl border bg-card/50 p-4 text-sm">
          <p>
            LangSmith tracing:{' '}
            <strong>{ops.data.langsmith_tracing ? 'on' : 'off'}</strong> (project{' '}
            {ops.data.langsmith_project})
          </p>
          {ops.data.langsmith_url ? (
            <a className="mt-2 inline-block underline" href={ops.data.langsmith_url} target="_blank" rel="noreferrer">
              Open LangSmith project
            </a>
          ) : (
            <p className="mt-2 text-muted-foreground">
              Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY on the API to link traces.
            </p>
          )}
          <ul className="mt-4 flex flex-wrap gap-2">
            {Object.entries(ops.data.cache_by_task).map(([task, n]) => (
              <li key={task} className="rounded-full bg-muted px-3 py-1 text-xs">
                {task}: {n} cached
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-card/80 p-4 shadow-sm backdrop-blur">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  )
}

function FadeIn({
  children,
  delay = false,
  className = '',
}: {
  children: ReactNode
  delay?: boolean
  className?: string
}) {
  return (
    <div
      className={`animate-fade-up ${delay ? '[animation-delay:120ms]' : ''} ${className}`}
    >
      {children}
    </div>
  )
}
