import { Lock } from 'lucide-react'

import type { AttributeStatus } from '../../api/types'
import { cn } from '../../lib/cn'
import { accentText, type Accent } from '../../navigation'
import { AnimatedNumber } from './AnimatedNumber'
import { ProgressRing } from './ProgressRing'

interface AttributeBadgeProps {
  /** Discipline, Knowledge, Strength, Stamina, Agility, Recovery... */
  name: string
  /** Normalised 0-100, or null when there is no honest number yet. */
  score: number | null
  /**
   * Why there is no score. An attribute is never silently rendered as 0 - that
   * would make "no data" look identical to "did nothing", which is the exact
   * dishonesty the scoring engine exists to avoid. See docs/SCORING.md.
   */
  status?: AttributeStatus
  /** Short explanation shown in place of the score: "R3", "2 more days". */
  hint?: string
  /** 0-1. Dims the ring when a score rests on little history. */
  confidence?: number
  accent?: Accent
  size?: number
  className?: string
}

/** One RPG attribute, shown as a ring. The radar chart shows them together. */
export function AttributeBadge({
  name,
  score,
  status = 'active',
  hint,
  confidence,
  accent = 'brand',
  size = 84,
  className,
}: AttributeBadgeProps) {
  const hasScore = status === 'active' && typeof score === 'number'
  const locked = status === 'locked'

  return (
    <div className={cn('flex flex-col items-center gap-2', className)}>
      <ProgressRing
        value={hasScore ? score : 0}
        size={size}
        thickness={7}
        accent={accent}
        ariaLabel={
          hasScore
            ? `${name}: ${Math.round(score)} out of 100`
            : `${name}: ${hint ?? status}`
        }
        label={
          hasScore ? (
            <AnimatedNumber
              value={Math.round(score)}
              className={cn('tabular text-section font-bold', accentText[accent])}
            />
          ) : locked ? (
            <Lock className="size-4 text-ink-subtle" aria-hidden />
          ) : (
            <span className="text-section font-bold text-ink-subtle" aria-hidden>
              –
            </span>
          )
        }
        // A score built on four days should not look as solid as one built on forty.
        className={cn(
          !hasScore && 'opacity-55',
          hasScore && typeof confidence === 'number' && confidence < 0.5 && 'opacity-75',
        )}
      />
      <div className="flex flex-col items-center gap-0.5">
        <span className="text-meta text-ink-muted">{name}</span>
        {hint && <span className="text-caption text-ink-subtle">{hint}</span>}
      </div>
    </div>
  )
}
