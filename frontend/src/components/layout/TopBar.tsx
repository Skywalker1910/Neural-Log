import { Flame } from 'lucide-react'

import { useCurrentUser, useGamificationSummary } from '../../api/queries'
import { Skeleton } from '../ui/Skeleton'

function greeting(hour: number): string {
  if (hour < 5) return 'Still up'
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

const DATE_FORMAT: Intl.DateTimeFormatOptions = {
  weekday: 'long',
  month: 'long',
  day: 'numeric',
}

/**
 * Identity + progression strip. This is also the first real proof that the SPA's
 * cookie-authenticated API calls work through the Vite proxy.
 */
export function TopBar() {
  const now = new Date()
  const user = useCurrentUser()
  const summary = useGamificationSummary()

  const xpPct =
    summary.data && summary.data.xp_for_next_level > 0
      ? Math.min(100, (summary.data.xp_into_level / summary.data.xp_for_next_level) * 100)
      : 0

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-line px-4 lg:px-6">
      <div className="min-w-0">
        <h1 className="truncate text-label font-semibold text-ink">
          {greeting(now.getHours())}
          {user.data ? `, ${user.data.username}` : ''}
        </h1>
        <p className="truncate text-meta text-ink-subtle">
          {now.toLocaleDateString(undefined, DATE_FORMAT)}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-4">
        {summary.isPending ? (
          <Skeleton className="h-8 w-32" />
        ) : summary.data ? (
          <>
            {summary.data.current_streak > 0 && (
              <span
                className="hidden items-center gap-1.5 text-label text-discipline sm:flex"
                title={`${summary.data.current_streak} day streak`}
              >
                <Flame size={16} aria-hidden />
                <span className="tabular">{summary.data.current_streak}</span>
              </span>
            )}

            <div className="hidden w-40 sm:block">
              <div className="flex items-baseline justify-between text-meta">
                <span className="font-semibold text-ink">Level {summary.data.level}</span>
                <span className="tabular text-ink-subtle">
                  {summary.data.xp_into_level}/{summary.data.xp_for_next_level}
                </span>
              </div>
              <div
                className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-raised"
                role="progressbar"
                aria-valuenow={Math.round(xpPct)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Progress to next level"
              >
                <div
                  className="h-full rounded-full bg-discipline transition-[width] duration-500"
                  style={{ width: `${xpPct}%` }}
                />
              </div>
            </div>

            <span className="flex size-9 items-center justify-center rounded-full bg-discipline/12 text-label font-bold text-discipline sm:hidden">
              {summary.data.level}
            </span>
          </>
        ) : null}
      </div>
    </header>
  )
}
