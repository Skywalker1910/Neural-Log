import {
  BookOpen,
  Brain,
  ClipboardList,
  Code,
  Coffee,
  Croissant,
  Crown,
  Dumbbell,
  Footprints,
  GlassWater,
  Moon,
  NotebookPen,
  Salad,
  ShieldCheck,
  Sparkles,
  Star,
  Sun,
  Target,
  User,
  Users,
  type LucideIcon,
} from 'lucide-react'

import { cn } from '../../lib/cn'
import type { ItemIconKey } from '../../lib/itemIcons'
import { accentBg, accentText, type Accent } from '../../navigation'

const ICONS: Record<ItemIconKey, LucideIcon> = {
  // The server's own keys.
  sun: Sun,
  coffee: Coffee,
  workout: Dumbbell,
  code: Code,
  chess: Crown,
  breakfast: Croissant,
  lunch: Salad,
  water: GlassWater,
  sleep: Moon,
  default: Sparkles,
  // Inferred by iconForItem() when the server had no opinion.
  task: Target,
  journal: NotebookPen,
  plan: ClipboardList,
  rating: Star,
  reading: BookOpen,
  mind: Brain,
  steps: Footprints,
  people: Users,
  admin: ShieldCheck,
  user: User,
}

/** A default accent per key, so a checklist reads as categories at a glance
 *  rather than as one undifferentiated column of grey. */
const ACCENTS: Record<ItemIconKey, Accent> = {
  sun: 'discipline',
  coffee: 'discipline',
  workout: 'fitness',
  code: 'learning',
  chess: 'learning',
  breakfast: 'lifestyle',
  lunch: 'lifestyle',
  water: 'recovery',
  sleep: 'recovery',
  default: 'brand',
  task: 'discipline',
  journal: 'goals',
  plan: 'goals',
  rating: 'discipline',
  reading: 'learning',
  mind: 'recovery',
  steps: 'fitness',
  people: 'lifestyle',
  admin: 'brand',
  user: 'brand',
}

interface ItemIconProps {
  name: ItemIconKey
  size?: number
  /** Dimmed treatment for a locked achievement or an unanswered item. */
  locked?: boolean
  /** Overrides the key's default accent. */
  accent?: Accent
  className?: string
  label?: string
}

/**
 * Icons for checklist items and the other places that used to carry hand-drawn
 * artwork.
 *
 * That artwork was PNG line art drawn for a light ground, which meant every one
 * of them had to sit on a pale disc to be visible at all - a row of white
 * circles punched through a black UI. It also could not take a colour, could not
 * scale past its raster size, and cost a network request each.
 *
 * A line icon from the same family as the rest of the chrome inherits currentColor,
 * stays sharp at any size, and ships in a bundle that is already loaded.
 */
export function ItemIcon({
  name,
  size = 40,
  locked = false,
  accent,
  className,
  label,
}: ItemIconProps) {
  const Icon = ICONS[name] ?? ICONS.default
  const tone = accent ?? ACCENTS[name] ?? 'brand'

  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-md',
        locked ? 'bg-surface-raised text-ink-subtle' : cn(accentBg[tone], accentText[tone]),
        className,
      )}
      style={{ width: size, height: size }}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {/* 0.5 keeps the glyph optically centred in its tile at every size. */}
      <Icon size={Math.round(size * 0.5)} strokeWidth={1.75} />
    </span>
  )
}
