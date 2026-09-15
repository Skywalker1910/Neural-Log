import { useMemo } from 'react'

import { cn } from '../../lib/cn'
import { shortDate } from '../../lib/date'
import type { CalendarCell } from '../../api/types'

/**
 * Adherence, one square per day.
 *
 * Deliberately not XP. XP is capped and multiplied, so a perfect day inside a
 * ten-day streak outscores an identical day on day one - which would make the
 * grid brighter on the right for reasons that have nothing to do with how the
 * day went. Completion means the same thing on every square.
 *
 * Not Recharts either: this is a CSS grid of divs. Recharts has no heatmap, and
 * pulling 300kB in to draw coloured rectangles would be absurd.
 */

interface CalendarHeatmapProps {
  cells: CalendarCell[]
  /** Called when a day is clicked - used to open that day's log. */
  onSelect?: (date: string) => void
}

/**
 * Five bands rather than a continuous gradient. A continuous scale looks
 * precise but nobody can read 63% out of a shade, and the extra resolution
 * mostly renders as noise at 12px per square.
 */
function band(cell: CalendarCell): { className: string; label: string } {
  // An unlogged day has to be *visible* as an empty square. surface-card is the
  // card's own background, so it rendered as nothing at all - a grid of two
  // green dots floating in space, with no sense of the days around them.
  if (!cell.logged) return { className: 'bg-surface-raised', label: 'not logged' }
  const pct = cell.completion_pct ?? 0
  if (pct >= 90) return { className: 'bg-lifestyle', label: `${pct}% complete` }
  if (pct >= 70) return { className: 'bg-lifestyle/70', label: `${pct}% complete` }
  if (pct >= 40) return { className: 'bg-lifestyle/45', label: `${pct}% complete` }
  if (pct > 0) return { className: 'bg-lifestyle/25', label: `${pct}% complete` }
  return { className: 'bg-surface-overlay', label: 'logged, nothing completed' }
}

const WEEKDAYS = ['Mon', '', 'Wed', '', 'Fri', '', 'Sun']

/** Monday-first weekday index, because the grid reads as weeks. */
function weekdayIndex(iso: string): number {
  const [y, m, d] = iso.split('-').map(Number)
  return (new Date(y, m - 1, d).getDay() + 6) % 7
}

export function CalendarHeatmap({ cells, onSelect }: CalendarHeatmapProps) {
  /*
    Columns are weeks, rows are weekdays - the GitHub arrangement, which works
    because a year fits in 53 columns while 53 rows would not fit on a screen.
    The first column is padded so every row is genuinely the same weekday;
    without that the grid still renders, but diagonally, and reading "I never
    log on Sundays" out of it becomes impossible.
  */
  const { weeks, leading } = useMemo(() => {
    if (cells.length === 0) return { weeks: [] as (CalendarCell | null)[][], leading: 0 }

    const pad = weekdayIndex(cells[0].date)
    const padded: (CalendarCell | null)[] = [...Array(pad).fill(null), ...cells]
    const out: (CalendarCell | null)[][] = []
    for (let i = 0; i < padded.length; i += 7) {
      const week = padded.slice(i, i + 7)
      while (week.length < 7) week.push(null)
      out.push(week)
    }
    return { weeks: out, leading: pad }
  }, [cells])

  if (cells.length === 0) return null

  return (
    <div className="flex flex-col gap-3">
      {/* overflow-x-auto so a year of columns scrolls inside the card instead of
          widening the page - the min-width:auto trap, again. */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        <div className="flex shrink-0 flex-col gap-1 pt-0.5">
          {WEEKDAYS.map((day, index) => (
            <span
              key={index}
              className="flex h-3.5 items-center text-caption leading-none text-ink-subtle"
            >
              {day}
            </span>
          ))}
        </div>

        <div className="flex gap-1">
          {weeks.map((week, weekIndex) => (
            <div key={weekIndex} className="flex flex-col gap-1">
              {week.map((cell, dayIndex) => {
                if (!cell) {
                  return <span key={dayIndex} className="size-3.5" aria-hidden />
                }
                const { className, label } = band(cell)
                const interactive = Boolean(onSelect)
                return (
                  <button
                    key={cell.date}
                    type="button"
                    disabled={!interactive}
                    onClick={() => onSelect?.(cell.date)}
                    title={`${shortDate(cell.date)} - ${label}`}
                    aria-label={`${shortDate(cell.date)}, ${label}`}
                    className={cn(
                      'size-3.5 rounded-[3px] transition-transform duration-150 ease-apple',
                      className,
                      interactive && 'hover:scale-125 focus-visible:scale-125',
                    )}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 text-meta text-ink-subtle">
        <span>Less</span>
        <span className="size-3 rounded-[3px] bg-surface-raised" />
        <span className="size-3 rounded-[3px] bg-lifestyle/25" />
        <span className="size-3 rounded-[3px] bg-lifestyle/45" />
        <span className="size-3 rounded-[3px] bg-lifestyle/70" />
        <span className="size-3 rounded-[3px] bg-lifestyle" />
        <span>More</span>
        {leading > 0 && <span className="sr-only">Grid starts mid-week.</span>}
      </div>
    </div>
  )
}
