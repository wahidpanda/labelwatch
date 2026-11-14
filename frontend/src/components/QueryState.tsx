import type { UseQueryResult } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { ApiError } from '@/api/client'

export function QueryState<T>({
  query,
  label,
  children,
}: {
  query: UseQueryResult<T>
  label: string
  children: (data: T) => ReactNode
}) {
  if (query.isPending) {
    return (
      <p role="status" className="text-muted-foreground">
        Loading {label}…
      </p>
    )
  }
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404
    return (
      <p role="alert" className="text-destructive">
        {notFound ? `No ${label} found.` : `Could not load ${label}: ${query.error.message}`}
      </p>
    )
  }
  return <>{children(query.data)}</>
}
