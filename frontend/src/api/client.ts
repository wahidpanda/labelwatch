import createClient from 'openapi-fetch'

import type { components, paths } from '@/api/schema'

export type Schemas = components['schemas']
export type DrugSummary = Schemas['DrugSummary']
export type EventSummary = Schemas['EventSummary']
export type EventDetail = Schemas['EventDetail']
export type JudgementOut = Schemas['JudgementOut']
export type DrugMatrix = Schemas['DrugMatrix']
export type StaleGeneric = Schemas['StaleGeneric']
export type Overview = Schemas['Overview']
export type Methodology = Schemas['Methodology']
export type Status = JudgementOut['status']

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

// Resolve fetch per call so tests can stub it after this module loads.
export const api = createClient<paths>({
  baseUrl: API_BASE_URL,
  fetch: (request) => globalThis.fetch(request),
})

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

/** Unwrap an openapi-fetch result, turning problem+json errors into ApiError. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call
  if (data === undefined) {
    const detail =
      typeof error === 'object' && error !== null && 'detail' in error
        ? String((error).detail)
        : response.statusText || 'Request failed'
    throw new ApiError(response.status, detail)
  }
  return data
}
