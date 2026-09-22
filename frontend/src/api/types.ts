/**
 * Response shapes for the endpoints Flask already serves (app.py).
 *
 * Hand-written rather than generated: there are ~8 of them today and a codegen
 * step would be more machinery than it's worth. Revisit if the API grows past
 * what's comfortable to keep in sync by hand.
 */
import type { Accent } from '../navigation'

export interface CurrentUser {
  user_id: number
  username: string
  is_admin: boolean
  selected_path: string
  selected_path_id: string | null
  /** Hidden from the leaderboard at this account's own request. */
  leaderboard_opt_out: boolean
}

export interface AdminUser {
  id: number
  username: string
  email: string | null
  is_admin: boolean
  is_active: boolean
  leaderboard_opt_out: boolean
  created_at: string
  activity_count: number
  logged_days: number
  last_logged_on: string | null
  total_xp: number
}

export interface AdminOverview {
  accounts: {
    total: number
    active: number
    admins: number
    active_this_week: number
  }
  logging: {
    activities: number
    days: number
  }
  features: {
    workouts: number
    meals: number
    learning_sessions: number
    goals: number
    habits: number
  }
  registration_mode: 'open' | 'invite' | 'closed'
  database_integrity: string
  /** The release this instance is running, from the VERSION file. */
  version: string
  /** The commit the image was built from. 'unknown' outside CI. */
  commit: string
  backup: BackupStatus
}

/**
 * What the nightly backup script said about itself.
 *
 * Every field is a claim made by something the app does not run, so `known`
 * gates the rest: a fresh instance has no status file, and that is not the same
 * as a failure. Reporting "FAILED" at somebody on their first afternoon teaches
 * them to ignore the indicator, which costs more than saying nothing would.
 */
export interface BackupStatus {
  known: boolean
  /** Why nothing is known, when `known` is false. */
  reason?: string
  ok?: boolean
  /**
   * Whether the snapshot left the instance.
   *
   * Separate from `ok` on purpose. A backup written successfully to the same
   * disk as the database defends against deleting the wrong thing, and not at
   * all against losing the instance.
   */
  offsite?: boolean
  finished_at?: string | null
  age_hours?: number | null
  /** Older than a missed run's worth of grace. */
  stale?: boolean
  message?: string
  users?: number | null
  logged_days?: number | null
  local_copies?: number | null
}

/**
 * What the assistant has cost, for the admin page.
 *
 * `estimated` is always true and the UI must say so. These dollars are computed
 * from configurable rates so a spend cap can be enforced before a request is
 * made - something the provider's own billing, which lags and reports the whole
 * organisation, cannot do. The invoice remains the authority.
 */
export interface AiUsageReport {
  days: number
  estimated: boolean
  configured: boolean
  chat_model: string
  extraction_model: string
  monthly_budget_usd: number
  totals: {
    calls: number
    failures: number
    input_tokens: number
    output_tokens: number
    cached_input_tokens: number
    estimated_cost_usd: number
  }
  by_feature: { feature: string; calls: number; estimated_cost_usd: number }[]
  by_day: { day: string; calls: number; estimated_cost_usd: number }[]
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

export type AchievementCategory =
  | 'consistency' | 'training' | 'nutrition' | 'lifestyle' | 'learning' | 'mastery'

export type AchievementTier = 'bronze' | 'silver' | 'gold'

/**
 * R7 turned badges from opaque earned/not-earned flags into something that can
 * report progress: `current` of `threshold`. A locked achievement can say
 * "180 of 600 minutes" rather than sitting greyed out with no hint.
 */
export interface Badge {
  code: string
  name: string
  description: string
  earned: boolean
  category: AchievementCategory
  tier: AchievementTier
  xp_reward: number
  current: number
  threshold: number
  /** 0-1. Always 1 once earned. */
  progress: number
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
  /**
   * You opted out, so you are not in `entries`.
   *
   * Without this the page cannot tell "nobody has any XP yet" apart from "you
   * asked to be hidden", and the second one looks exactly like a bug.
   */
  viewer_hidden: boolean
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
  /** null on a day the checklist was not submitted - unobserved, not zero. */
  daily_score: number | null
  discipline_score: number | null
  completion_pct: number
  /** Whether the day was actually submitted. */
  logged: boolean
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
  /**
   * Which of the seventeen movement shapes this is, so the UI can animate it.
   * Keyed to the movement rather than the exercise: a barbell, dumbbell and
   * machine chest press are one movement done three ways.
   */
  movement_pattern: string | null
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
  /**
   * Display unit only: 'g' or 'ml'. Storage and every macro calculation stay in
   * grams, and 1 ml is taken as 1 g - true to within ~3% for water-based drinks
   * and milk, which is well inside the error already in "one mug". Oils keep
   * grams: at 0.92 g/ml, ml would misstate them by 8%.
   */
  unit: 'g' | 'ml'
  /**
   * Grams in one cup, where a standard measure exists. null means the UI must
   * not offer cups: a cup is a volume and grams a mass, so the factor depends on
   * what is in the cup.
   */
  grams_per_cup: number | null
  /** Counted rather than weighed - eggs, fruit. serving_grams is one piece. */
  is_countable: boolean
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
  /** The food's display unit, joined through from `foods`. */
  unit?: 'g' | 'ml'
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
  instructions: string[]
  ingredients: RecipeIngredient[]
  food: Food | null
}

export interface WeeklyFeedDay {
  date: string
  calories: number | null
  protein_g: number | null
  sessions: number
  sets: number
  volume: number
  sleep_minutes: number | null
  water_ml: number | null
  steps: number | null
  mood: number | null
  study_minutes: number
}

export interface WeeklyFeed {
  range: { start: string; end: string }
  days: WeeklyFeedDay[]
  totals: Record<string, number | null>
  insights: { tone: 'info' | 'success' | 'warning'; title: string; body: string }[]
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

/* --- R5: learning --------------------------------------------------------- */

export interface LearningArea {
  id: number
  name: string
  /** A design-system accent name, so an area is coloured consistently. */
  accent: string
  notes: string | null
  /** Null means the profile-wide weekly study target applies instead. */
  weekly_target_minutes: number | null
  /** Joined on the list endpoint only. */
  topic_count?: number
  total_minutes?: number
}

export interface LearningTopic {
  id: number
  area_id: number | null
  name: string
  notes: string | null
  status: 'active' | 'paused' | 'done'
  area_name?: string | null
  area_accent?: string | null
  session_count?: number
  total_minutes?: number
  last_studied?: string | null
}

export interface LearningSession {
  id: number
  date: string
  topic_id: number | null
  /**
   * HH:MM. Optional - but when present they are what let two sessions fifteen
   * minutes apart count as one interrupted block rather than two short ones,
   * which is the difference between an honest Focus score and a punitive one.
   */
  started_at: string | null
  ended_at: string | null
  duration_minutes: number
  /** 1-5, self-reported. Recorded and charted, deliberately never scored. */
  focus_rating: number | null
  difficulty: number | null
  notes: string | null
  topic_name?: string | null
  area_name?: string | null
  area_accent?: string | null
}

export interface LearningSummary {
  recent: LearningSession[]
  by_day: { date: string; minutes: number; sessions: number }[]
  by_topic: {
    topic: string
    area: string
    accent: string
    minutes: number
    sessions: number
  }[]
  totals: {
    sessions: number
    minutes: number
    this_week_minutes: number
    weekly_target_minutes: number
    streak_days: number
    /** Duration-weighted mean block length, as a % of the target block. */
    depth_pct: number | null
    target_block_minutes: number
  }
}

export interface LearningAreasResponse {
  areas: LearningArea[]
}

export interface LearningTopicsResponse {
  topics: LearningTopic[]
}

export interface LearningSessionsResponse {
  sessions: LearningSession[]
}

/* --- R6: habits, goals and tasks ------------------------------------------ */

export type ScheduleType = 'daily' | 'weekdays' | 'days' | 'times-per-week'

export interface HabitStat {
  id: number
  slug: string
  name: string
  icon: string
  weight: number
  schedule_type: ScheduleType
  /** Weekday indices, Monday = 0. */
  schedule_days: number[]
  target_per_week: number | null
  group_slug: string
  group_name: string
  /** Days with an answer of any kind in the window. */
  logged: number
  /** Days the answer counted as done. */
  done: number
  avg_credit: number
  streak: number
}

export interface HabitsResponse {
  habits: HabitStat[]
  window_days: number
  /** 'selected' is the path you are following; 'all' is every path's items. */
  scope: 'selected' | 'all'
}

export type GoalCategory =
  | 'fitness' | 'learning' | 'lifestyle' | 'career' | 'finance' | 'other'

export type GoalStatus = 'active' | 'paused' | 'achieved' | 'abandoned'

export interface Milestone {
  id: number
  goal_id: number
  title: string
  target_date: string | null
  position: number
  /** Null means not done. A date, so "when did I pass this" stays answerable. */
  completed_on: string | null
}

export interface Task {
  id: number
  goal_id: number | null
  title: string
  notes: string | null
  due_date: string | null
  /** 1 high, 2 normal, 3 low. */
  priority: number
  completed_on: string | null
  goal_title?: string | null
  goal_accent?: string | null
}

/**
 * Where a goal's progress number came from, most evidenced first. The UI must
 * never present a self-reported number as if it were measured - see
 * migrations/007_goals.sql.
 */
export interface GoalProgress {
  percent: number | null
  source: 'habits' | 'milestones' | 'metric' | 'none'
  linked_habits: {
    habit_id: number
    name: string
    done: number
    elapsed_days: number
    adherence: number
  }[]
}

export interface Goal {
  id: number
  title: string
  description: string | null
  category: GoalCategory
  accent: string
  status: GoalStatus
  target_date: string | null
  metric_name: string | null
  target_value: number | null
  current_value: number
  started_on: string | null
  achieved_on: string | null
  days_remaining: number | null
  milestones: Milestone[]
  tasks: Task[]
  habit_ids: number[]
  progress: GoalProgress
}

export interface GoalsSummary {
  goals: Goal[]
  tasks: Task[]
  habits: { id: number; name: string; icon: string; group_name: string }[]
  totals: {
    active: number
    achieved: number
    overdue: number
    due_soon: number
    open_tasks: number
  }
}

export interface GoalsResponse {
  goals: Goal[]
}

export interface TasksResponse {
  tasks: Task[]
}

/* --- R7: the XP ledger ---------------------------------------------------- */

export type XpSource =
  | 'checklist' | 'training' | 'nutrition' | 'lifestyle' | 'learning' | 'badge'

export interface XpEntry {
  id: number
  date: string
  source: XpSource
  source_key: string
  /** Human-readable. The ledger exists to answer "why did I get that". */
  reason: string
  base_xp: number
  multiplier_pct: number
  xp: number
  /** Set when a daily cap reduced this award, holding what it would have been. */
  capped_from: number | null
  /** 'measured' for logged work, 'claimed' for a ticked box. */
  evidence: 'measured' | 'claimed'
}

export interface XpLedger {
  entries: XpEntry[]
  by_source: { source: XpSource; xp: number; entries: number }[]
  evidence: Partial<Record<'measured' | 'claimed', number>>
  total_xp: number
  caps: {
    per_source: Record<string, number>
    daily_total: number
  }
}

/* --- R8: analytics -------------------------------------------------------- */

export type MetricAggregate = 'sum' | 'avg'

export interface MetricPoint {
  date: string
  /** null means *unobserved*, never zero. Charts must gap rather than plot 0. */
  value: number | null
}

export interface AnalyticsMetric {
  key: string
  label: string
  unit: string
  accent: Accent
  aggregate: MetricAggregate
  /** Fixed y-axis range for bounded scales, e.g. [0, 100]. */
  domain: [number, number] | null
  value: number | null
  previous: number | null
  delta: number | null
  delta_pct: number | null
  /** Days with data, out of `days`. The denominator an average should be read with. */
  observed_days: number
  previous_observed_days: number
  days: number
  series: MetricPoint[]
}

export interface CalendarCell {
  date: string
  logged: boolean
  completion_pct: number | null
  items_completed: number | null
  items_total: number | null
  daily_score: number | null
}

export interface AttributeComparison {
  attribute: string
  score: number | null
  previous: number | null
  delta: number | null
  status: string
  sample_days: number
}

export type AnalyticsPeriod = '7' | '30' | '90' | '365' | 'all'

export interface AnalyticsResponse {
  period: AnalyticsPeriod
  range: { start: string; end: string; days: number; label: string }
  previous: { start: string; end: string; days: number }
  metrics: AnalyticsMetric[]
  calendar: CalendarCell[]
  attributes: AttributeComparison[]
  days_logged: number
}

/* --- R9: onboarding ------------------------------------------------------- */

export interface OnboardingStep {
  key: string
  title: string
  blurb: string
  fields: string[]
}

/** Every answer the flow collects. All nullable - a skipped step is a real state. */
export interface OnboardingAnswers {
  birth_year: number | null
  sex: string | null
  height_cm: number | null
  activity_level: string | null
  training_days_per_week: number | null
  goal: string | null
  sleep_target_minutes: number | null
  target_bedtime: string | null
  target_wake_time: string | null
  weekly_study_minutes: number | null
  weight_kg: number | null
}

export interface Baselines {
  bmi: number | null
  bmr: number | null
  tdee: number | null
  age: number | null
  weight_kg: number | null
  height_cm: number | null
  /** What is still needed, so the UI can say why a baseline is blank. */
  missing: string[]
}

export interface NutritionTargets {
  calories: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  fibre_g: number
  water_ml: number
  steps: number
  sleep_minutes: number
  weekly_study_minutes: number
  estimated_tdee: number | null
  estimated_bmr: number | null
  goal: string
  /** Per-target: 'set' (chosen), 'estimated' (derived), or 'unknown'. */
  sources: Record<string, 'set' | 'estimated' | 'unknown'>
}

export interface OnboardingState {
  steps: OnboardingStep[]
  /** The shared daily survey, shown on its own step rather than chosen. */
  survey: ChecklistItem[]
  step: number
  completed: boolean
  completed_at: string | null
  dismissed: boolean
  /** Server-derived so every client agrees about when to show the banner. */
  should_prompt: boolean
  answers: OnboardingAnswers
  baselines: Baselines
  targets: NutritionTargets
}
