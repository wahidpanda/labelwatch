import type { Status } from '@/api/client'

export const STATUS_LABEL: Record<Status, string> = {
  propagated: 'Reflected',
  partial: 'Partly reflected',
  not_propagated: 'Not yet reflected',
  insufficient_evidence: 'Unclear',
}
