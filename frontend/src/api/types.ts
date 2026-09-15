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

/* --- R3: training --------------------------------------------------------- */

export type MuscleGroup =
  | 'chest' | 'back' | 'shoulders' | 'biceps' | 'triceps' | 'quads'
  | 'hamstrings' | 'glutes' | 'calves' | 'core' | 'forearms' | 'full-body' | 'cardio'

export type ExerciseCategory = 'strength' | 'cardio' | 'mobility'

export interface Exercise {
  id: number
  slug: string
  name: string
  primary_muscle: MuscleGroup
  secondary_muscles: MuscleGroup[]
  equipment: string
  category: ExerciseCategory
  difficulty: 'beginner' | 'intermediate' | 'advanced'
  is_compound: boolean
  instructions: string[]
  is_custom: boolean
}

export interface LoggedSet {
  id?: number
  exercise_id: number
  exercise_name?: string
  primary_muscle?: MuscleGroup
  category?: ExerciseCategory
  position?: number
  weight?: number | null
  weight_unit?: string
  reps?: number | null
  duration_seconds?: number | null
  rpe?: number | null
  /** Real work, but excluded from volume and records - it is not the signal. */
  is_warmup?: boolean
  completed?: boolean
}

export interface Workout {
  id: number
  date: string
  name: string | null
  notes: string | null
  routine_id: number | null
  duration_seconds: number | null
  total_volume: number
  total_sets: number
  finished_at: string | null
  sets: LoggedSet[]
}

export interface SetRecord {
  weight: number
  weight_unit: string
  reps: number
  date: string
}

export interface ExerciseHistory {
  exercise_id: number
  last_session_date: string | null
  last_session_sets: LoggedSet[]
  /** "Best" means two things in a gym, so both are reported. */
  heaviest_set: SetRecord | null
  best_volume_set: SetRecord | null
  recent_sets: LoggedSet[]
}

export interface ExercisesResponse {
  exercises: Exercise[]
}

export interface RoutineExercise {
  id?: number
  exercise_id: number
  position?: number
  target_sets: number | null
  target_reps: number | null
  notes?: string | null
  /** Joined from the library so the client never has to look the name up. */
  name?: string
  category?: ExerciseCategory
  primary_muscle?: MuscleGroup
}

export interface Routine {
  id: number
  name: string
  split_type: string | null
  notes: string | null
  archived: boolean
  exercises: RoutineExercise[]
}

export interface RoutinesResponse {
  routines: Routine[]
}

export interface TrainingSummary {
  total_sessions: number
  total_volume: number
  recent: Workout[]
  volume_trend: { date: string; volume: number; sessions: number }[]
  by_muscle: { muscle: MuscleGroup; sets: number; volume: number }[]
  records: {
    exercise: string
    exercise_id: number
    weight: number
    weight_unit: string
    reps: number
    date: string
  }[]
  measurements: { metric: string; value: number; unit: string | null; date: string }[]
}

/* --- R4: nutrition and lifestyle ------------------------------------------ */

export type FoodCategory =
  | 'protein' | 'grain' | 'legume' | 'vegetable' | 'fruit' | 'dairy' | 'fat'
  | 'nut-seed' | 'beverage' | 'prepared' | 'condiment' | 'sweet'

export type Meal = 'breakfast' | 'lunch' | 'dinner' | 'snack'

export interface Food {
  id: number
  slug: string
  name: string
  category: FoodCategory
  /** 'library' ships with the app, 'custom' you added, 'recipe' you cooked. */
  source: 'library' | 'custom' | 'recipe'
  kcal_per_100g: number
  protein_per_100g: number
  carbs_per_100g: number
  fat_per_100g: number
  fibre_per_100g: number
  serving_name: string | null
  serving_grams: number | null
  is_custom: boolean
}

export interface Macros {
  calories: number
  protein_g: number
  carbs_g: number
  fat_g: number
  fibre_g: number
}

export interface FoodEntry {
  id: number
  food_id: number
  name: string
  category: FoodCategory
  source: Food['source']
  meal: Meal
  grams: number
  serving_name: string | null
  serving_grams: number | null
  macros: Macros
}

/** Every value is either what you set or a derivation - `sources` says which. */
export interface Targets {
  calories: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  fibre_g: number
  water_ml: number
  steps: number
  sleep_minutes: number
  estimated_tdee: number | null
  estimated_bmr: number | null
  goal: 'cut' | 'maintain' | 'bulk'
  sources: Record<string, 'set' | 'estimated' | 'unknown'>
}

export interface NutritionDay {
  date: string
  entries: FoodEntry[]
  by_meal: Partial<Record<Meal, FoodEntry[]>>
  totals: Macros
  targets: Targets
  body_weight_kg: number | null
}

export interface RecipeIngredient {
  id?: number
  food_id: number
  grams: number
  position?: number
  name?: string
  category?: FoodCategory
  kcal_per_100g?: number
  protein_per_100g?: number
  carbs_per_100g?: number
  fat_per_100g?: number
  fibre_per_100g?: number
}

export interface Recipe {
  id: number
  /** The `foods` row this recipe produces - what you actually log. */
  food_id: number
  name: string
  servings: number
  /** Cooked weight. Not the sum of the raw ingredients. */
  total_grams: number | null
  notes: string | null
  ingredients: RecipeIngredient[]
  food: Food | null
}

export interface SleepEntry {
  id?: number
  /** The date you WOKE UP - a night spans two calendar dates. */
  date: string
  bedtime: string | null
  wake_time: string | null
  duration_minutes: number
  /** 1-5, self-reported. Recorded, never scored. */
  quality: number | null
  notes: string | null
}

export interface LifestyleDay {
  date: string
  water_ml: number | null
  steps: number | null
  sunlight_minutes: number | null
  /** 1-5, self-reported feelings. Charted, never scored. */
  mood: number | null
  stress: number | null
  energy: number | null
  journal: string | null
}

export interface LifestyleDayResponse {
  date: string
  lifestyle: LifestyleDay | null
  sleep: SleepEntry | null
  targets: Targets
}

export interface LifestyleSummary {
  sleep: SleepEntry[]
  lifestyle: LifestyleDay[]
  targets: Targets
  averages: {
    sleep_minutes: number | null
    schedule_consistency: number | null
    water_ml: number | null
    steps: number | null
  }
}

export interface UserProfile {
  birth_year: number | null
  sex: 'male' | 'female' | 'unspecified' | null
  height_cm: number | null
  activity_level: 'sedentary' | 'light' | 'moderate' | 'active' | 'very-active'
  goal: 'cut' | 'maintain' | 'bulk'
  calorie_target: number | null
  protein_target_g: number | null
  carb_target_g: number | null
  fat_target_g: number | null
  fibre_target_g: number | null
  water_target_ml: number | null
  step_target: number | null
  sleep_target_minutes: number | null
}

export interface ProfileResponse {
  profile: Partial<UserProfile>
  targets: Targets
  body_weight_kg: number | null
}

export interface FoodsResponse {
  foods: Food[]
}

export interface RecipesResponse {
  recipes: Recipe[]
}
