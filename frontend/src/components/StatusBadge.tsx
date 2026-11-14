import { CircleCheck, CircleDashed, CircleHelp, CircleX } from 'lucide-react'

import type { Status } from '@/api/client'
import { STATUS_LABEL } from '@/lib/status'
import { cn } from '@/lib/utils'

const STYLE: Record<Status, string> = {
  propagated: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100',
  partial: 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-100',
  not_propagated: 'bg-rose-100 text-rose-900 dark:bg-rose-950 dark:text-rose-100',
  insufficient_evidence: 'bg-muted text-muted-foreground',
}

const ICON = {
  propagated: CircleCheck,
  partial: CircleDashed,
  not_propagated: CircleX,
  insufficient_evidence: CircleHelp,
} as const

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const Icon = ICON[status]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
        STYLE[status],
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      {STATUS_LABEL[status]}
    </span>
  )
}
