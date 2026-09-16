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
 * Identity + progression strip.
 *
 * Sticky and frosted rather than a fixed panel: your level and streak are the
 * two numbers worth keeping on screen at all times, and Apple's answer to
 * "always visible but never in the way" is a material you can see through.
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
    <header className="material-chrome sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-4 border-b border-line px-4 lg:px-8">
      <div className="min-w-0">
        {/*
          A <p>, not an <h1>. The bar is chrome that persists across every route,
          so heading it competes with the page's own title - two h1s on every
          screen, which is what the audit found. The page owns the h1.
        */}
        <p className="truncate text-label font-semibold tracking-tight text-ink">
          {greeting(now.getHours())}
          {user.data ? `, ${user.data.username}` : ''}
        </p>
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
                className="hidden items-center gap-1.5 rounded-pill bg-discipline/12 px-3 py-1 text-label text-discipline sm:flex"
                title={`${summary.data.current_streak} day streak`}
              >
                <Flame size={15} strokeWidth={2} aria-hidden />
                <span className="tabular">{summary.data.current_streak}</span>
              </span>
            )}

            <div className="hidden w-40 sm:block">
              <div className="flex items-baseline justify-between text-meta">
                <span className="font-semibold tracking-tight text-ink">
                  Level {summary.data.level}
                </span>
                <span className="tabular text-ink-subtle">
                  {summary.data.xp_into_level}/{summary.data.xp_for_next_level}
                </span>
              </div>
              <div
                className="mt-1.5 h-1.5 overflow-hidden rounded-pill bg-surface-raised"
                role="progressbar"
                aria-valuenow={Math.round(xpPct)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Progress to next level"
              >
                <div
                  className="h-full rounded-pill bg-discipline transition-[width] duration-700 ease-apple"
                  style={{ width: `${xpPct}%` }}
                />
              </div>
            </div>

            <span className="flex size-9 items-center justify-center rounded-pill bg-discipline/12 text-label font-bold text-discipline sm:hidden">
              {summary.data.level}
            </span>
          </>
        ) : null}
      </div>
    </header>
  )
}
