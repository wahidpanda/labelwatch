import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { RouterProvider } from 'react-router'

import { App } from '@/app/App'
import { createQueryClient } from '@/app/queryClient'
import { createTestRouter } from '@/app/router'

function renderAt(path: string) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={createTestRouter(path)} />
    </QueryClientProvider>,
  )
}

describe('app shell', () => {
  it('renders the dashboard placeholder with KPI cards', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByText('Drugs tracked')).toBeInTheDocument()
    expect(screen.getByLabelText('Median lag (days): no data yet')).toBeInTheDocument()
    expect(document.title).toBe('Dashboard · Label Lag Radar')
  })

  it('always shows the not-medical-advice notice and date caveat', () => {
    renderAt('/')
    expect(screen.getByText('Not medical advice. Not a regulatory finding.')).toBeInTheDocument()
    expect(screen.getByText(/DailyMed publication dates, not FDA approval dates/)).toBeInTheDocument()
  })

  it('boots the production app with the browser router', () => {
    render(<App />)
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument()
  })

  it('shows a not-found page for unknown routes', () => {
    renderAt('/does-not-exist')
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to the dashboard' })).toHaveAttribute('href', '/')
  })
})
