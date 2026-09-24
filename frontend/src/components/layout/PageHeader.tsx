import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { LifeIllustration, type IllustrationKind } from '../ui/LifeIllustration'
import { SectionIllustration, type SectionArt } from '../ui/SectionIllustration'
import type { Accent } from '../../navigation'

const STORIES: Partial<Record<IllustrationKind, { tagline: string }>> = {
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
  storyKind?: IllustrationKind
  illustration?: SectionArt
}

export function PageHeader({ title, description, icon, accent = 'brand', actions, storyKind, illustration }: PageHeaderProps) {
  const story = storyKind ? STORIES[storyKind] : undefined
  return (
    <section className={`page-hero hero-${storyKind || accent}`} aria-label={title}>
      <div className="page-hero-head">
        <div className="page-hero-identity">
          <span className="page-hero-anim">
            {storyKind ? <LifeIllustration kind={storyKind} /> : <SectionIllustration kind={illustration} icon={icon} />}
          </span>
          <div className="page-hero-copy">
            <h1>{title}</h1>
            {story && <p className="page-hero-tagline">{story.tagline}</p>}
            {description && <p className={story ? 'page-hero-desc' : 'page-hero-tagline'}>{description}</p>}
          </div>
        </div>
        {actions && <div className="page-hero-actions">{actions}</div>}
      </div>
    </section>
  )
}
