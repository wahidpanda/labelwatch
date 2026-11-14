import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { RouterProvider } from 'react-router'

import { App } from '@/app/App'
import { createQueryClient } from '@/app/queryClient'
import { createTestRouter } from '@/app/router'

const DRUG_ID = '00000000-0000-4000-8000-000000000001'
const EVENT_ID = '00000000-0000-4000-8000-000000000002'
const JUDGEMENT_ID = '00000000-0000-4000-8000-000000000003'
const SETID = '00000000-0000-4000-8000-000000000004'

const genericSet = { setid: SETID, title: 'MONTELUKAST [ACME]', labeler: 'ACME', is_repackager: false }
const counts = { propagated: 1, partial: 0, not_propagated: 0, insufficient_evidence: 0 }

const RESPONSES: Record<string, unknown> = {
  '/api/v1/stats/overview': {
    drugs: 2,
    events: 55,
    judgements: 120,
    median_lag_days: 182,
    stale_generics: 12,
    stale_share: 0.1,
    last_ingestion_at: '2026-11-14T02:10:05Z',
  },
  '/api/v1/drugs': {
    items: [
      {
        id: DRUG_ID,
        ingredient: 'montelukast',
        drug_class: null,
        events: 16,
        generics: 14,
        stale_generics: 3,
        median_lag_days: 210,
        p90_lag_days: 400,
        last_event_date: '2021-06-01',
      },
    ],
    next_cursor: null,
  },
  [`/api/v1/drugs/${DRUG_ID}`]: {
    id: DRUG_ID,
    ingredient: 'montelukast',
    drug_class: null,
    events: 16,
    generics: 14,
    stale_generics: 3,
    median_lag_days: 210,
    p90_lag_days: 400,
    last_event_date: '2021-06-01',
  },
  [`/api/v1/drugs/${DRUG_ID}/matrix`]: {
    events: [
      {
        id: EVENT_ID,
        event_date: '2021-06-01',
        section_key: 'boxed_warning',
        severity: 'boxed',
        claim_text: 'Boxed warning for neuropsychiatric events added.',
      },
    ],
    rows: [
      {
        generic_set: genericSet,
        cells: { [EVENT_ID]: { judgement_id: JUDGEMENT_ID, status: 'propagated', lag_days: 120 } },
      },
    ],
  },
  [`/api/v1/events/${EVENT_ID}`]: {
    id: EVENT_ID,
    drug_id: DRUG_ID,
    ingredient: 'montelukast',
    event_date: '2021-06-01',
    section_key: 'boxed_warning',
    change_type: 'added',
    severity: 'boxed',
    claim_text: 'Boxed warning for neuropsychiatric events added.',
    brand_unit: 'Serious neuropsychiatric events have been reported.',
    brand_setid: SETID,
    brand_title: 'SINGULAIR',
    brand_version: 1,
    counts,
  },
  [`/api/v1/events/${EVENT_ID}/judgements`]: {
    items: [
      {
        id: JUDGEMENT_ID,
        event_id: EVENT_ID,
        generic_set: genericSet,
        status: 'propagated',
        lag_days: 120,
        first_version: { number: 3, date: '2021-09-29' },
        confidence: 0.9,
        method: 'llm',
        model: 'google_genai:gemini',
        non_monotonic: false,
        evidence: { quotes: ['Neuropsychiatric events have been reported in patients.'] },
      },
    ],
    next_cursor: null,
  },
  '/api/v1/generics/stale': {
    items: [
      {
        judgement_id: JUDGEMENT_ID,
        generic_set: genericSet,
        event_id: EVENT_ID,
        event_date: '2021-06-01',
        claim_text: 'Boxed warning for neuropsychiatric events added.',
        days_since_event: 1992,
        latest_version_date: '2024-01-01',
      },
    ],
    next_cursor: null,
  },
  '/api/v1/methodology': {
    prompt_version: 'v1',
    stale_days: 90,
    limits: ['Dates are DailyMed publication dates.'],
    disclaimer: 'This is research data about label text, not medical advice.',
  },
}

beforeEach(() => {
  vi.stubGlobal('fetch', (input: Request) => {
    const path = new URL(input.url).pathname
    const body = RESPONSES[path]
    if (body === undefined) {
      return Promise.resolve(
        new Response(JSON.stringify({ status: 404, detail: 'Not found' }), {
          status: 404,
          headers: { 'Content-Type': 'application/problem+json' },
        }),
      )
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }),
    )
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderAt(path: string) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={createTestRouter(path)} />
    </QueryClientProvider>,
  )
}

describe('app', () => {
  it('dashboard shows live KPIs and the drug table', async () => {
    renderAt('/')
    expect(screen.getByRole('heading', { level: 1, name: 'Label lag overview' })).toBeInTheDocument()
    expect(await screen.findByLabelText('Median lag: 182 days')).toBeInTheDocument()
    expect(screen.getByLabelText('Not yet reflected: 10%')).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Montelukast' })).toHaveAttribute(
      'href',
      `/drugs/${DRUG_ID}`,
    )
    expect(document.title).toBe('Dashboard · Label Lag Radar')
  })

  it('drug page renders the heatmap with text labels, not colour alone', async () => {
    renderAt(`/drugs/${DRUG_ID}`)
    expect(await screen.findByRole('heading', { level: 1, name: 'Montelukast' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Reflected, 120 days' })).toHaveAttribute(
      'href',
      `/events/${EVENT_ID}#j-${JUDGEMENT_ID}`,
    )
  })

  it('event page shows brand text and verified generic quotes', async () => {
    renderAt(`/events/${EVENT_ID}`)
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: 'Boxed warning for neuropsychiatric events added.',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('Serious neuropsychiatric events have been reported.')).toBeInTheDocument()
    expect(
      await screen.findByText('Neuropsychiatric events have been reported in patients.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/First reflected in version 3/)).toBeInTheDocument()
  })

  it('stale page lists generics and offers a CSV download', async () => {
    renderAt('/stale')
    expect(await screen.findByText('1,992')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download CSV' }).getAttribute('href')).toMatch(
      /\/api\/v1\/generics\/stale\?format=csv$/,
    )
  })

  it('methodology page lists limits and the disclaimer', async () => {
    renderAt('/methodology')
    expect(await screen.findByText('Dates are DailyMed publication dates.')).toBeInTheDocument()
    expect(screen.getByText(/not medical advice/)).toBeInTheDocument()
  })

  it('unknown drug shows a not-found message', async () => {
    renderAt('/drugs/00000000-0000-4000-8000-00000000ffff')
    expect(await screen.findByRole('alert')).toHaveTextContent('No drug found.')
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
  })
})
