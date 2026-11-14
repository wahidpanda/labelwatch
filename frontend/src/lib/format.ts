import { useEffect } from 'react'

export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · Label Lag Radar`
  }, [title])
}

export function formatDays(days: number | null | undefined): string {
  if (days === null || days === undefined) return '—'
  return `${Math.round(days).toLocaleString('en-US')} days`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(`${value.slice(0, 10)}T00:00:00Z`).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

export function formatPercent(share: number | null | undefined): string {
  if (share === null || share === undefined) return '—'
  return `${Math.round(share * 100)}%`
}

export function sectionName(key: string): string {
  return key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

export function title(text: string): string {
  return text.replace(/\b\w/g, (c) => c.toUpperCase())
}
