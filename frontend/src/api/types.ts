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

/* --- R2: attributes, days, home ------------------------------------------ */

/**
 * An attribute never silently becomes a number. See docs/SCORING.md:
 *   locked      - no data source exists yet; `unlocks_in` names the phase
 *   unobserved  - nothing in your Path feeds it
 *   calibrating - observed, but on too little history; `needs_days` remains
 *   active      - a real score
 */
export type AttributeStatus = 'locked' | 'unobserved' | 'calibrating' | 'active'

export interface AttributeScore {
  attribute: string
  status: AttributeStatus
  /** Null unless status is 'active' - 0 would be indistinguishable from "did nothing". */
  score: number | null
  confidence: number
  sample_days: number
  raw_value?: number | null
  unlocks_in?: string
  needs_days?: number
}

export interface AttributesResponse {
  date: string | null
  attributes: AttributeScore[]
}

/** One checklist item as it was on a given day, from the daily_log snapshot. */
export interface DayItem {
  name: string
  type: string
  icon: string
  weight: number
  response: string | null
  /** 0.0-1.0. Graded for ordinal 'time' answers, unlike the binary XP path. */
  credit: number
  attributes: Record<string, number>
}

export interface DayDetail {
  date: string
  logged: boolean
  path?: { id: string | null; name: string | null }
  completion_pct?: number
  items_total?: number
  items_completed?: number
  self_rating?: number | null
  notes?: string | null
  items: DayItem[]
  scores: {
    daily_score: number | null
    discipline_score: number | null
    completion_pct: number
  } | null
}

export interface DailyScorePoint {
  date: string
  daily_score: number | null
  discipline_score: number | null
  completion_pct: number
}

export interface HomeSummary {
  date: string
  level: number
  total_xp: number
  xp_into_level: number
  xp_for_next_level: number
  current_streak: number
  streak_multiplier_pct: number
  days_logged: number
  daily_score: number | null
  discipline_score: number | null
  today: {
    logged: boolean
    completion_pct: number
    items_total: number
    items_completed: number
  }
  attributes: AttributeScore[]
  trend: DailyScorePoint[]
}

export interface ChecklistItemsResponse {
  success: boolean
  items: ChecklistItem[]
}

export interface SaveDayRequest {
  /** Keyed by item NAME - that is how the backend joins answers to items. */
  responses: Record<string, string>
  path_id?: string
  path_name?: string
  notes?: string
  self_rating?: number
}

export interface SaveDayResponse {
  date: string
  completion_pct: number
  newly_earned_badges: Badge[]
}
