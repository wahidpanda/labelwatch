import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { RouterProvider } from 'react-router'

import { createQueryClient } from '@/app/queryClient'
import { createTestRouter } from '@/app/router'

const DRUG_ID = '00000000-0000-4000-8000-000000000001'
const EVENT_ID = '00000000-0000-4000-8000-000000000002'

const EMPTY: Record<string, unknown> = {
  '/api/v1/stats/overview': {
    drugs: 0,
    events: 0,
    judgements: 0,
    median_lag_days: null,
    stale_generics: 0,
    stale_share: null,
    last_ingestion_at: null,
  },
  '/api/v1/drugs': { items: [], next_cursor: null },
  [`/api/v1/drugs/${DRUG_ID}`]: {
    id: DRUG_ID,
    ingredient: 'warfarin',
    drug_class: null,
    events: 0,
    generics: 0,
    stale_generics: 0,
    median_lag_days: null,
    p90_lag_days: null,
    last_event_date: null,
  },
  [`/api/v1/drugs/${DRUG_ID}/matrix`]: { events: [], rows: [] },
  [`/api/v1/events/${EVENT_ID}`]: {
    id: EVENT_ID,
    drug_id: DRUG_ID,
    ingredient: 'warfarin',
    event_date: '2013-03-15',
    section_key: 'adverse_reactions',
    change_type: 'added',
    severity: 'major',
    claim_text: 'Skin necrosis was added.',
    brand_unit: 'Necrosis of skin has been reported.',
    brand_setid: DRUG_ID,
    brand_title: 'COUMADIN',
    brand_version: 2,
    counts: { propagated: 0, partial: 0, not_propagated: 1, insufficient_evidence: 0 },
  },
  [`/api/v1/events/${EVENT_ID}/judgements`]: {
    items: [
      {
        id: EVENT_ID,
        event_id: EVENT_ID,
        generic_set: { setid: DRUG_ID, title: 'WARFARIN [X]', labeler: null, is_repackager: false },
        status: 'not_propagated',
        lag_days: null,
        first_version: null,
        confidence: null,
        method: 'baseline_lexical',
        model: null,
        non_monotonic: true,
        evidence: {},
      },
    ],
    next_cursor: null,
  },
  '/api/v1/generics/stale': { items: [], next_cursor: null },
}

function stub(status = 200) {
  vi.stubGlobal('fetch', (input: Request) => {
    const body = EMPTY[new URL(input.url).pathname]
    if (status !== 200 || body === undefined) {
      return Promise.resolve(
        new Response(JSON.stringify({ status, detail: 'Database unavailable' }), {
          status: status === 200 ? 404 : status,
          headers: { 'Content-Type': 'application/problem+json' },
        }),
      )
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }),
    )
  })
}

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

describe('empty and error states', () => {
  it('dashboard with no data', async () => {
    stub()
    renderAt('/?q=zzz')
    expect(await screen.findByText('No drugs match.')).toBeInTheDocument()
    expect(screen.getByLabelText('Median lag: —')).toBeInTheDocument()
    expect(screen.getByRole('searchbox')).toHaveValue('zzz')
  })

  it('drug with no events', async () => {
    stub()
    renderAt(`/drugs/${DRUG_ID}`)
    expect(await screen.findByText('No brand safety events detected yet.')).toBeInTheDocument()
  })

  it('event not yet reflected anywhere, with a dropped-claim note', async () => {
    stub()
    renderAt(`/events/${EVENT_ID}`)
    expect(
      await screen.findByText(/No published version reflects this change yet/),
    ).toBeInTheDocument()
    expect(screen.getByText(/later one dropped it/)).toBeInTheDocument()
  })

  it('stale list empty', async () => {
    stub()
    renderAt('/stale')
    expect(await screen.findByText('Nothing is past the threshold.')).toBeInTheDocument()
  })

  it('server errors are announced', async () => {
    stub(503)
    renderAt('/stale')
    expect(await screen.findByRole('alert', {}, { timeout: 4000 })).toHaveTextContent(
      'Could not load stale generics: Database unavailable',
    )
  })
})
