import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { LifeIllustration, type IllustrationKind } from '../ui/LifeIllustration'
import { cn } from '../../lib/cn'
import { accentBg, accentText, type Accent } from '../../navigation'

const STORIES: Record<string, { tagline: string }> = {
  training: { tagline: 'Every set feeds Strength, Stamina and Agility.' },
  nutrition: { tagline: 'Hitting your targets feeds Discipline.' },
  lifestyle: { tagline: 'Sleep, steps and schedule shape your Recovery.' },
}

interface PageHeaderProps {
  title: string
  description?: ReactNode
  icon?: LucideIcon
  accent?: Accent
  actions?: ReactNode
  /** When provided, renders a combined hero box with the illustration, story text, and actions inside. */
  storyKind?: IllustrationKind
}

export function PageHeader({ title, description, icon: Icon, accent = 'brand', actions, storyKind }: PageHeaderProps) {
  if (storyKind && STORIES[storyKind]) {
    const story = STORIES[storyKind]
    return (
      <section className={`page-hero hero-${storyKind}`} aria-label={title}>
        <div className="page-hero-head">
          <div className="page-hero-identity">
            <span className="page-hero-anim">
              <LifeIllustration kind={storyKind} />
            </span>
            <div>
              <h1>{title}</h1>
              <p className="page-hero-tagline">{story.tagline}</p>
              {description && <p className="page-hero-desc">{description}</p>}
            </div>
          </div>
          {actions && <div className="page-hero-actions">{actions}</div>}
        </div>
      </section>
    )
  }

  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 items-center gap-3">
        {Icon && (
          <span
            className={cn(
              'flex size-11 shrink-0 items-center justify-center rounded-lg',
              accentBg[accent],
              accentText[accent],
            )}
          >
            <Icon size={22} aria-hidden />
          </span>
        )}
        <div className="min-w-0">
          <h1 className="text-heading text-ink">{title}</h1>
          {description && <p className="mt-0.5 text-label text-ink-muted">{description}</p>}
        </div>
      </div>
      {actions && (
        <div className="flex max-w-full shrink-0 flex-wrap items-center gap-2">{actions}</div>
      )}
    </div>
  )
}
