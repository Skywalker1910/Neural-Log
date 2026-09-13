import {
  Activity,
  CalendarCheck,
  ChartLine,
  Dumbbell,
  GraduationCap,
  House,
  HeartPulse,
  Settings,
  Target,
  Trophy,
  User,
  UtensilsCrossed,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/**
 * Category accents (design tokens) are identity for sections and data - not for
 * ordinary UI chrome, which stays neutral or uses the single brand accent.
 */
export type Accent = 'brand' | 'fitness' | 'learning' | 'lifestyle' | 'goals' | 'discipline' | 'recovery'

/**
 * Tailwind scans source for *literal* class strings, so accent classes have to be
 * spelled out here rather than built as `text-${accent}` at runtime.
 */
export const accentText: Record<Accent, string> = {
  brand: 'text-brand',
  fitness: 'text-fitness',
  learning: 'text-learning',
  lifestyle: 'text-lifestyle',
  goals: 'text-goals',
  discipline: 'text-discipline',
  recovery: 'text-recovery',
}

export const accentBg: Record<Accent, string> = {
  brand: 'bg-brand/12',
  fitness: 'bg-fitness/12',
  learning: 'bg-learning/12',
  lifestyle: 'bg-lifestyle/12',
  goals: 'bg-goals/12',
  discipline: 'bg-discipline/12',
  recovery: 'bg-recovery/12',
}

export const accentStroke: Record<Accent, string> = {
  brand: 'var(--color-brand)',
  fitness: 'var(--color-fitness)',
  learning: 'var(--color-learning)',
  lifestyle: 'var(--color-lifestyle)',
  goals: 'var(--color-goals)',
  discipline: 'var(--color-discipline)',
  recovery: 'var(--color-recovery)',
}

export interface NavSection {
  label: string
  path: string
  icon: LucideIcon
  accent: Accent
  /** Shown in the mobile bottom bar rather than the overflow sheet. */
  primary?: boolean
  /** One-liner used by the placeholder pages until the phase that builds it lands. */
  blurb: string
  phase: number
}

export const NAV_SECTIONS: NavSection[] = [
  {
    label: 'Home',
    path: '/',
    icon: House,
    accent: 'brand',
    primary: true,
    blurb: 'Your command centre: level, discipline score, streaks and today at a glance.',
    phase: 2,
  },
  {
    label: 'Today',
    path: '/today',
    icon: CalendarCheck,
    accent: 'discipline',
    primary: true,
    blurb: 'Everything planned for today - routines, training, learning, meals - in one timeline.',
    phase: 2,
  },
  {
    label: 'Training',
    path: '/training',
    icon: Dumbbell,
    accent: 'fitness',
    primary: true,
    blurb: 'Routines, the exercise library, set-by-set logging and strength progression.',
    phase: 3,
  },
  {
    label: 'Nutrition',
    path: '/nutrition',
    icon: UtensilsCrossed,
    accent: 'lifestyle',
    primary: true,
    blurb: 'Calories, macros, hydration and energy balance against your estimated TDEE.',
    phase: 4,
  },
  {
    label: 'Lifestyle',
    path: '/lifestyle',
    icon: HeartPulse,
    accent: 'recovery',
    blurb: 'Sleep, steps, hydration, mood and the habits that quietly drive everything else.',
    phase: 4,
  },
  {
    label: 'Learning',
    path: '/learning',
    icon: GraduationCap,
    accent: 'learning',
    blurb: 'Subjects, skills, tracked study sessions and knowledge progression.',
    phase: 5,
  },
  {
    label: 'Goals',
    path: '/goals',
    icon: Target,
    accent: 'goals',
    blurb: 'Long and short term goals, milestones and the habits that feed them.',
    phase: 6,
  },
  {
    label: 'Achievements',
    path: '/achievements',
    icon: Trophy,
    accent: 'discipline',
    blurb: 'Badges earned and still locked, across discipline, fitness and learning.',
    phase: 7,
  },
  {
    label: 'Analytics',
    path: '/analytics',
    icon: ChartLine,
    accent: 'learning',
    blurb: 'Long-range trends: discipline, training volume, study hours, sleep, body metrics.',
    phase: 8,
  },
  {
    label: 'Profile',
    path: '/profile',
    icon: User,
    accent: 'brand',
    blurb: 'Your attributes, body metrics, baseline estimates and personal details.',
    phase: 9,
  },
]

export const SETTINGS_SECTION: NavSection = {
  label: 'Settings',
  path: '/settings',
  icon: Settings,
  accent: 'brand',
  blurb: 'Units, targets, reminders and account preferences.',
  phase: 9,
}

/** Dev-only gallery proving every primitive renders against the tokens. */
export const DESIGN_SECTION: NavSection = {
  label: 'Design system',
  path: '/_design',
  icon: Activity,
  accent: 'brand',
  blurb: 'Component gallery for the design system.',
  phase: 1,
}

export const PRIMARY_SECTIONS = NAV_SECTIONS.filter((section) => section.primary)
export const OVERFLOW_SECTIONS = NAV_SECTIONS.filter((section) => !section.primary)
