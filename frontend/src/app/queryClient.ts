import { QueryClient } from '@tanstack/react-query'

import { ApiError } from '@/api/client'

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000,
        retry: (failures, error) =>
          !(error instanceof ApiError && error.status < 500) && failures < 1,
        refetchOnWindowFocus: false,
      },
    },
  })
}
