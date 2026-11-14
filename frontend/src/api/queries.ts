import { useQuery } from '@tanstack/react-query'

import { api, unwrap } from '@/api/client'

export function useOverview() {
  return useQuery({
    queryKey: ['overview'],
    queryFn: () => unwrap(api.GET('/api/v1/stats/overview')),
  })
}

export function useDrugs(q: string) {
  return useQuery({
    queryKey: ['drugs', q],
    queryFn: () =>
      unwrap(api.GET('/api/v1/drugs', { params: { query: { q: q || null, limit: 100 } } })),
  })
}

export function useDrug(drugId: string) {
  return useQuery({
    queryKey: ['drug', drugId],
    queryFn: () =>
      unwrap(api.GET('/api/v1/drugs/{drug_id}', { params: { path: { drug_id: drugId } } })),
  })
}

export function useDrugMatrix(drugId: string) {
  return useQuery({
    queryKey: ['matrix', drugId],
    queryFn: () =>
      unwrap(api.GET('/api/v1/drugs/{drug_id}/matrix', { params: { path: { drug_id: drugId } } })),
  })
}

export function useEvent(eventId: string) {
  return useQuery({
    queryKey: ['event', eventId],
    queryFn: () =>
      unwrap(api.GET('/api/v1/events/{event_id}', { params: { path: { event_id: eventId } } })),
  })
}

export function useEventJudgements(eventId: string) {
  return useQuery({
    queryKey: ['event-judgements', eventId],
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/events/{event_id}/judgements', {
          params: { path: { event_id: eventId }, query: { limit: 100 } },
        }),
      ),
  })
}

export function useStale() {
  return useQuery({
    queryKey: ['stale'],
    queryFn: () => unwrap(api.GET('/api/v1/generics/stale', { params: { query: { limit: 100 } } })),
  })
}

export function useMethodology() {
  return useQuery({
    queryKey: ['methodology'],
    queryFn: () => unwrap(api.GET('/api/v1/methodology')),
    staleTime: Infinity,
  })
}
