import {
  Award, BookOpen, CalendarCheck, ChefHat, Crown, Dumbbell, Flame, Footprints,
  GraduationCap, HeartPulse, Medal, Moon, Mountain, NotebookPen, Receipt,
  Route, ShieldCheck, Sparkles, Star, Sun, Target, Trophy, UtensilsCrossed, Weight,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type { AchievementCategory, Badge } from '../../api/types'

const ICONS: Record<string, LucideIcon> = {
  'first-log': Footprints, 'week-streak': Flame, 'month-streak': Crown,
  century: Trophy, 'custom-path': Route, 'perfect-day': Star,
  'level-5': Award, 'level-10': Mountain, 'evidence-1000': Receipt, 'goal-achieved': Target,
  'first-workout': Dumbbell, 'workouts-25': Medal, 'workouts-100': ShieldCheck, 'volume-100k': Weight,
  'first-study': BookOpen, 'study-10h': NotebookPen, 'study-100h': GraduationCap,
  'first-night': Moon, 'nights-30': Sun, 'steps-target-10': Footprints,
  'first-meal': UtensilsCrossed, 'food-30': CalendarCheck, 'first-recipe': ChefHat,
}

const CATEGORY_ICONS: Record<AchievementCategory, LucideIcon> = {
  consistency: Flame, training: Dumbbell, nutrition: UtensilsCrossed,
  lifestyle: HeartPulse, learning: BookOpen, mastery: Sparkles,
}

export function AchievementEmblem({ achievement, compact = false }: { achievement: Badge; compact?: boolean }) {
  const Icon = ICONS[achievement.code] ?? CATEGORY_ICONS[achievement.category] ?? Trophy
  const stars = achievement.tier === 'gold' ? 3 : achievement.tier === 'silver' ? 2 : 1

  return <div aria-hidden="true" className={`achievement-emblem emblem-${achievement.tier}${achievement.earned ? '' : ' emblem-locked'}${compact ? ' emblem-compact' : ''}`}>
    <div className="emblem-ribbons"><span /><span /></div>
    <div className="emblem-seal"><div className="emblem-core">
      <Icon size={compact ? 25 : 36} strokeWidth={1.5} />
      <span className="emblem-stars">{Array.from({ length: stars }, (_, index) => <Star key={index} size={8} fill="currentColor" />)}</span>
    </div></div>
  </div>
}
