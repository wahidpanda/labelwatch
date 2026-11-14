import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router'

import { createQueryClient } from '@/app/queryClient'
import { createAppRouter } from '@/app/router'
import { AuthGate } from '@/components/AuthGate'

const queryClient = createQueryClient()
const router = createAppRouter()

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthGate>
        <RouterProvider router={router} />
      </AuthGate>
    </QueryClientProvider>
  )
}
