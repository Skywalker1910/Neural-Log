/**
 * Response shapes for the endpoints Flask already serves (app.py).
 *
 * Hand-written rather than generated: there are ~8 of them today and a codegen
 * step would be more machinery than it's worth. Revisit if the API grows past
 * what's comfortable to keep in sync by hand.
 */

export interface CurrentUser {
  user_id: number
  username: string
  is_admin: boolean
  selected_path: string
  selected_path_id: string | null
}

export interface ActivityByDate {
  date: string
  count: number
  avg_score: number | null
}

export interface Stats {
  total_days: number
  total_activities: number
  current_streak: number
  avg_score: number
  activities_by_date: ActivityByDate[]
}

export interface Badge {
  code: string
  name: string
  description: string
  earned: boolean
}

export interface GamificationSummary {
  total_xp: number
  level: number
  xp_into_level: number
  xp_for_next_level: number
  current_streak: number
  streak_multiplier_pct: number
  badges: Badge[]
}

export interface LeaderboardEntry {
  rank: number
  username: string
  total_xp: number
  level: number
  current_streak: number
}

export interface Leaderboard {
  scope: 'overall' | 'monthly'
  entries: LeaderboardEntry[]
}

export interface ChecklistItem {
  id: string
  name: string
  type: 'yes-no' | 'text' | 'rating' | 'time'
  icon: string
  weight: number
  options?: string[]
  subResponse?: {
    prompt: string
    type: 'radio' | 'checkbox'
    options: string[]
  }
}

export interface Path {
  id: string
  name: string
  is_default: boolean
  checklist_items: ChecklistItem[]
}

export interface PathsResponse {
  success: boolean
  paths: Path[]
  selected_path_id: string | null
  selected_path_name: string | null
}

export interface Activity {
  id: number
  user_id: number
  date: string
  activity_name: string
  description: string
  duration: number
  progress_score: number
  notes: string
  created_at: string
}
