import {
  Activity,
  LibraryBig,
  CalendarCheck,
  ChartLine,
  Dumbbell,
  GraduationCap,
  House,
  HeartPulse,
  Newspaper,
  Settings,
  ShieldCheck,
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
}

export const NAV_SECTIONS: NavSection[] = [
  {
    label: 'Home',
    path: '/',
    icon: House,
    accent: 'brand',
    primary: true,
  },
  {
    label: 'Today',
    path: '/today',
    icon: CalendarCheck,
    accent: 'discipline',
    primary: true,
  },
  {
    label: 'Training',
    path: '/training',
    icon: Dumbbell,
    accent: 'fitness',
    primary: true,
  },
  {
    label: 'Nutrition',
    path: '/nutrition',
    icon: UtensilsCrossed,
    accent: 'lifestyle',
    primary: true,
  },
  {
    label: 'Feed',
    path: '/feed',
    icon: Newspaper,
    accent: 'brand',
  },
  {
    label: 'Library',
    path: '/library',
    icon: LibraryBig,
    accent: 'goals',
  },
  {
    label: 'Lifestyle',
    path: '/lifestyle',
    icon: HeartPulse,
    accent: 'recovery',
  },
  {
    label: 'Learning',
    path: '/learning',
    icon: GraduationCap,
    accent: 'learning',
  },
  {
    label: 'Goals',
    path: '/goals',
    icon: Target,
    accent: 'goals',
  },
  {
    label: 'Achievements',
    path: '/achievements',
    icon: Trophy,
    accent: 'discipline',
  },
  {
    label: 'Analytics',
    path: '/analytics',
    icon: ChartLine,
    accent: 'learning',
  },
  {
    label: 'Profile',
    path: '/profile',
    icon: User,
    accent: 'brand',
  },
]

export const SETTINGS_SECTION: NavSection = {
  label: 'Settings',
  path: '/settings',
  icon: Settings,
  accent: 'brand',
}

export const ADMIN_SECTION: NavSection = {
  label: 'Admin',
  path: '/admin',
  icon: ShieldCheck,
  accent: 'brand',
}

/** Dev-only gallery proving every primitive renders against the tokens. */
export const DESIGN_SECTION: NavSection = {
  label: 'Design system',
  path: '/_design',
  icon: Activity,
  accent: 'brand',
}

export const PRIMARY_SECTIONS = NAV_SECTIONS.filter((section) => section.primary)
export const OVERFLOW_SECTIONS = NAV_SECTIONS.filter((section) => !section.primary)
