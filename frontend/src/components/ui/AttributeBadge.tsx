import { cn } from '../../lib/cn'
import { accentText, type Accent } from '../../navigation'
import { ProgressRing } from './ProgressRing'

interface AttributeBadgeProps {
  /** Discipline, Knowledge, Strength, Stamina, Agility, Recovery... */
  name: string
  /** Normalised 0-100 (see the scoring engine - Phase 2). */
  score: number
  accent?: Accent
  size?: number
  className?: string
}

/** One RPG attribute, shown as a ring. The radar chart shows them together. */
export function AttributeBadge({
  name,
  score,
  accent = 'brand',
  size = 84,
  className,
}: AttributeBadgeProps) {
  return (
    <div className={cn('flex flex-col items-center gap-2', className)}>
      <ProgressRing
        value={score}
        size={size}
        thickness={7}
        accent={accent}
        ariaLabel={name}
        label={
          <span className={cn('tabular text-section font-bold', accentText[accent])}>
            {Math.round(score)}
          </span>
        }
      />
      <span className="text-meta text-ink-muted">{name}</span>
    </div>
  )
}
