import { ApiError, unwrap } from '@/api/client'
import { createQueryClient } from '@/app/queryClient'
import { formatDate, formatDays, formatPercent, sectionName, title } from '@/lib/format'

describe('format helpers', () => {
  it('formats missing values as a dash', () => {
    expect(formatDays(null)).toBe('—')
    expect(formatDays(undefined)).toBe('—')
    expect(formatDate(null)).toBe('—')
    expect(formatDate('')).toBe('—')
    expect(formatPercent(null)).toBe('—')
  })

  it('formats values', () => {
    expect(formatDays(1234.4)).toBe('1,234 days')
    expect(formatDate('2021-06-01')).toBe('Jun 1, 2021')
    expect(formatDate('2026-11-14T02:10:05Z')).toBe('Nov 14, 2026')
    expect(formatPercent(0.456)).toBe('46%')
    expect(sectionName('warnings_precautions')).toBe('Warnings precautions')
    expect(title('warfarin sodium')).toBe('Warfarin Sodium')
  })
})

describe('api helpers', () => {
  it('unwrap returns data and turns problem bodies into ApiError', async () => {
    const ok = new Response('{}')
    await expect(unwrap(Promise.resolve({ data: 1, response: ok }))).resolves.toBe(1)

    const problem = new Response('', { status: 404 })
    await expect(
      unwrap(Promise.resolve({ error: { detail: 'Missing' }, response: problem })),
    ).rejects.toMatchObject({ status: 404, message: 'Missing' })

    const bare = new Response('', { status: 502, statusText: 'Bad Gateway' })
    await expect(unwrap(Promise.resolve({ error: 'x', response: bare }))).rejects.toBeInstanceOf(
      ApiError,
    )
  })

  it('retries server errors once but never client errors', () => {
    const retry = createQueryClient().getDefaultOptions().queries?.retry
    if (typeof retry !== 'function') throw new Error('retry should be a function')
    expect(retry(0, new ApiError(404, 'x'))).toBe(false)
    expect(retry(0, new ApiError(503, 'x'))).toBe(true)
    expect(retry(1, new ApiError(503, 'x'))).toBe(false)
    expect(retry(0, new Error('network'))).toBe(true)
  })
})
