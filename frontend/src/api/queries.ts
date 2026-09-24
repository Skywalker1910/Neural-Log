import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { AssistantState } from './assistant'
import { api } from './client'
import type {
  AnalyticsPeriod,
  OnboardingAnswers,
  OnboardingState,
  AnalyticsResponse,
  AttributesResponse,
  ChecklistItemsResponse,
  ExerciseHistory,
  ExercisesResponse,
  Food,
  FoodsResponse,
  LifestyleDay,
  LifestyleDayResponse,
  LearningArea,
  LearningAreasResponse,
  LearningSession,
  LearningSessionsResponse,
  LearningSummary,
  LearningTopic,
  LearningTopicsResponse,
  Goal,
  GoalsResponse,
  GoalStatus,
  GoalsSummary,
  HabitsResponse,
  HabitStat,
  Milestone,
  ScheduleType,
  Task,
  TasksResponse,
  XpLedger,
  LifestyleSummary,
  LoggedSet,
  NutritionDay,
  ProfileResponse,
  Recipe,
  RecipesResponse,
  Routine,
  RoutinesResponse,
  SleepEntry,
  TrainingSummary,
  UserProfile,
  Workout,
  WeeklyFeed,
  CurrentUser,
  AdminOverview,
  AiUsageReport,
  AdminUser,
  InviteCode,
  DayDetail,
  GamificationSummary,
  HomeSummary,
  Leaderboard,
  PathsResponse,
  SaveDayRequest,
  SaveDayResponse,
  Stats,
} from './types'

/** Query keys live in one place so cache invalidation stays greppable. */
export const queryKeys = {
  currentUser: ['current-user'] as const,
  stats: ['stats'] as const,
  gamification: ['gamification', 'summary'] as const,
  leaderboard: (scope: 'overall' | 'monthly') => ['leaderboard', scope] as const,
  paths: ['paths'] as const,
  home: ['home'] as const,
  attributes: (date?: string) => ['attributes', date ?? 'latest'] as const,
  day: (date: string) => ['day', date] as const,
  checklistItems: ['checklist-items'] as const,
  exercises: (filters?: string) => ['exercises', filters ?? 'all'] as const,
  exerciseHistory: (id: number, excludeSession?: number) =>
    ['exercise-history', id, excludeSession ?? null] as const,
  training: ['training'] as const,
  routines: ['routines'] as const,
  routine: (id: number) => ['routine', id] as const,
  workout: (id: number) => ['workout', id] as const,
  foods: (filters?: string) => ['foods', filters ?? 'all'] as const,
  recipes: ['recipes'] as const,
  nutrition: (date: string) => ['nutrition', date] as const,
  lifestyle: ['lifestyle'] as const,
  lifestyleDay: (date: string) => ['lifestyle-day', date] as const,
  sleep: ['sleep'] as const,
  profile: ['profile'] as const,
  learning: ['learning'] as const,
  learningAreas: ['learning-areas'] as const,
  learningTopics: ['learning-topics'] as const,
  learningSessions: ['learning-sessions'] as const,
  goals: ['goals'] as const,
  goalsSummary: ['goals', 'summary'] as const,
  tasks: ['tasks'] as const,
  habits: (days?: number) => ['habits', days ?? 'default'] as const,
  xpLedger: ['xp-ledger'] as const,
  analytics: (period: string) => ['analytics', period] as const,
  onboarding: ['onboarding'] as const,
  adminOverview: ['admin', 'overview'] as const,
  adminUsers: ['admin', 'users'] as const,
  adminAiUsage: (days: number) => ['admin', 'ai-usage', days] as const,
  adminInviteCodes: ['admin', 'invite-codes'] as const,
  assistantState: ['assistant', 'state'] as const,
  weeklyFeed: (end: string) => ['feed', 'weekly', end] as const,
}

/**
 * Whether this account appears on the leaderboard.
 *
 * Its own mutation rather than part of `useSaveProfile`, mirroring the endpoint:
 * saving the profile renames the account, and a privacy toggle should not be
 * able to fail because a username is taken.
 */
export function useSetLeaderboardVisibility() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (optOut: boolean) =>
      api.put<{ success: boolean; leaderboard_opt_out: boolean }>(
        '/api/user/privacy',
        { leaderboard_opt_out: optOut },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.currentUser })
      queryClient.invalidateQueries({ queryKey: ['leaderboard'] })
    },
  })
}

/**
 * Whether the assistant exists on this instance, and what it has cost you.
 *
 * Shared between the launcher and the Today page so the answer is fetched once.
 * `configured` is false when no API key is set, and both callers render nothing
 * rather than something disabled.
 */
export function useAssistantState() {
  return useQuery({
    queryKey: queryKeys.assistantState,
    queryFn: () => api.get<AssistantState>('/api/assistant/state'),
    staleTime: 5 * 60 * 1000,
  })
}

export function useWeeklyFeed(end: string) {
  return useQuery({
    queryKey: queryKeys.weeklyFeed(end),
    queryFn: () => api.get<WeeklyFeed>(`/api/feed/weekly?end=${end}`),
  })
}

export function useAdminAiUsage(days = 30) {
  return useQuery({
    queryKey: queryKeys.adminAiUsage(days),
    queryFn: () => api.get<AiUsageReport>(`/api/admin/ai-usage?days=${days}`),
  })
}

export function useCurrentUser() {
  return useQuery({
    queryKey: queryKeys.currentUser,
    queryFn: () => api.get<CurrentUser>('/api/current-user'),
    staleTime: 5 * 60_000,
  })
}

export function useAdminOverview() {
  return useQuery({
    queryKey: queryKeys.adminOverview,
    queryFn: () => api.get<AdminOverview>('/api/admin/stats'),
  })
}

export function useAdminUsers() {
  return useQuery({
    queryKey: queryKeys.adminUsers,
    queryFn: () => api.get<AdminUser[]>('/api/admin/users'),
  })
}

export function useAdminInviteCodes() {
  return useQuery({
    queryKey: queryKeys.adminInviteCodes,
    queryFn: () => api.get<InviteCode[]>('/api/admin/invite-codes'),
  })
}

export function useStats() {
  return useQuery({
    queryKey: queryKeys.stats,
    queryFn: () => api.get<Stats>('/api/stats'),
  })
}

export function useGamificationSummary() {
  return useQuery({
    queryKey: queryKeys.gamification,
    queryFn: () => api.get<GamificationSummary>('/api/gamification/summary'),
  })
}

export function useLeaderboard(scope: 'overall' | 'monthly') {
  return useQuery({
    queryKey: queryKeys.leaderboard(scope),
    queryFn: () => api.get<Leaderboard>(`/api/leaderboard/${scope}`),
  })
}

export function usePaths() {
  return useQuery({
    queryKey: queryKeys.paths,
    queryFn: () => api.get<PathsResponse>('/api/paths'),
  })
}

export function useHomeSummary() {
  return useQuery({
    queryKey: queryKeys.home,
    queryFn: () => api.get<HomeSummary>('/api/home'),
  })
}

export function useAttributes(date?: string) {
  return useQuery({
    queryKey: queryKeys.attributes(date),
    queryFn: () =>
      api.get<AttributesResponse>(date ? `/api/attributes?date=${date}` : '/api/attributes'),
  })
}

export function useDay(date: string) {
  return useQuery({
    queryKey: queryKeys.day(date),
    queryFn: () => api.get<DayDetail>(`/api/days/${date}`),
  })
}

export function useChecklistItems() {
  return useQuery({
    queryKey: queryKeys.checklistItems,
    queryFn: () => api.get<ChecklistItemsResponse>('/api/checklist-items'),
    staleTime: 5 * 60_000,
  })
}

export function useExercises(filters: { muscle?: string; category?: string; q?: string } = {}) {
  const params = new URLSearchParams(
    Object.entries(filters).filter(([, value]) => value) as [string, string][],
  ).toString()

  return useQuery({
    queryKey: queryKeys.exercises(params),
    queryFn: () =>
      api.get<ExercisesResponse>(`/api/exercises${params ? `?${params}` : ''}`),
    // The library only changes when the app ships a new one.
    staleTime: 30 * 60_000,
  })
}

/**
 * `excludeSession` keeps the session you are editing out of its own history, so
 * "last time" means the session before this one rather than the sets you just
 * typed. It is part of the cache key - the answer genuinely differs.
 */
export function useExerciseHistory(exerciseId: number | null, excludeSession?: number) {
  return useQuery({
    queryKey: queryKeys.exerciseHistory(exerciseId ?? 0, excludeSession),
    queryFn: () =>
      api.get<ExerciseHistory>(
        `/api/exercises/${exerciseId}/history${
          excludeSession ? `?exclude_session=${excludeSession}` : ''
        }`,
      ),
    enabled: exerciseId !== null,
  })
}

export function useTrainingSummary() {
  return useQuery({
    queryKey: queryKeys.training,
    queryFn: () => api.get<TrainingSummary>('/api/training'),
  })
}

export function useRoutines() {
  return useQuery({
    queryKey: queryKeys.routines,
    queryFn: () => api.get<RoutinesResponse>('/api/routines'),
  })
}

export function useRoutine(routineId: number | null) {
  return useQuery({
    queryKey: queryKeys.routine(routineId ?? 0),
    queryFn: () => api.get<Routine>(`/api/routines/${routineId}`),
    enabled: routineId !== null && routineId > 0,
  })
}

export function useSaveRoutine() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Routine> & { id?: number }) =>
      id
        ? api.put<Routine>(`/api/routines/${id}`, body)
        : api.post<Routine>('/api/routines', body),
    onSuccess: (routine) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.routines })
      queryClient.invalidateQueries({ queryKey: queryKeys.routine(routine.id) })
    },
  })
}

export function useDeleteRoutine() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (routineId: number) =>
      api.delete<{ success: boolean }>(`/api/routines/${routineId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.routines }),
  })
}

export function useWorkout(workoutId: number) {
  return useQuery({
    queryKey: queryKeys.workout(workoutId),
    queryFn: () => api.get<Workout>(`/api/workouts/${workoutId}`),
    enabled: Number.isFinite(workoutId) && workoutId > 0,
  })
}

export function useLogMeasurement() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { metric: string; date: string; value: number; unit?: string }) =>
      api.post<{ success: boolean }>('/api/measurements', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.training }),
  })
}

/**
 * Starting and saving a workout both move the training numbers AND the
 * attribute scores, so these invalidate the home/attribute keys too - a session
 * logged on the Training page has to show up on the radar without a reload.
 */
export function useStartWorkout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { date: string; name?: string; routine_id?: number }) =>
      api.post<Workout>('/api/workouts', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.training }),
  })
}

export function useSaveWorkout(workoutId: number | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Workout> & { sets?: LoggedSet[] }) =>
      api.put<Workout>(`/api/workouts/${workoutId}`, body),
    onSuccess: (workout) => {
      for (const key of [
        queryKeys.training,
        queryKeys.home,
        ['attributes'],
        queryKeys.workout(workout.id),
        ['exercise-history'],
      ]) {
        queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })
}

export function useDeleteWorkout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (workoutId: number) => api.delete<{ success: boolean }>(`/api/workouts/${workoutId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.training })
      queryClient.invalidateQueries({ queryKey: queryKeys.home })
      queryClient.invalidateQueries({ queryKey: ['attributes'] })
    },
  })
}

/**
 * Saving a day moves almost every number in the app - XP, level, streak,
 * attributes, the leaderboard - so this invalidates broadly rather than
 * surgically. `refetchOnWindowFocus` is off and `staleTime` is 30s, so nothing
 * self-heals; anything not invalidated here shows a stale value.
 */
export function useSaveDay(date: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: SaveDayRequest) => api.put<SaveDayResponse>(`/api/days/${date}`, body),
    onSuccess: () => {
      for (const key of [
        queryKeys.day(date),
        queryKeys.home,
        queryKeys.stats,
        queryKeys.gamification,
        ['attributes'],
        ['leaderboard'],
      ]) {
        queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })
}

/* --- R4: nutrition and lifestyle ------------------------------------------ */

/**
 * Logging a meal, a night's sleep or a step count moves attribute scores, so
 * every mutation here invalidates `home` and `attributes` alongside its own key.
 * `refetchOnWindowFocus` is off and `staleTime` is 30s, so nothing self-heals -
 * anything left out shows a stale number until a reload.
 */
function nutritionKeysFor(date: string) {
  return [
    queryKeys.nutrition(date),
    queryKeys.lifestyleDay(date),
    queryKeys.lifestyle,
    queryKeys.home,
    ['attributes'],
  ]
}

export function useFoods(filters: { q?: string; category?: string; source?: string } = {}) {
  const params = new URLSearchParams(
    Object.entries(filters).filter(([, value]) => value) as [string, string][],
  ).toString()

  return useQuery({
    queryKey: queryKeys.foods(params),
    queryFn: () => api.get<FoodsResponse>(`/api/foods${params ? `?${params}` : ''}`),
    // The shipped library only changes when the app ships a new one; a custom
    // food invalidates this key explicitly.
    staleTime: 30 * 60_000,
  })
}

export function useCreateFood() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Food> & { name: string; kcal_per_100g: number }) =>
      api.post<Food>('/api/foods', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['foods'] }),
  })
}

export function useNutritionDay(date: string) {
  return useQuery({
    queryKey: queryKeys.nutrition(date),
    queryFn: () => api.get<NutritionDay>(`/api/nutrition/${date}`),
  })
}

export function useLogFood(date: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { food_id: number; grams: number; meal: string }) =>
      api.post<{ success: boolean }>(`/api/nutrition/${date}/entries`, body),
    onSuccess: () => {
      for (const key of nutritionKeysFor(date)) {
        queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })
}

export function useUpdateFoodEntry(date: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; grams?: number; meal?: string }) =>
      api.put<{ success: boolean }>(`/api/nutrition/entries/${id}`, body),
    onSuccess: () => {
      for (const key of nutritionKeysFor(date)) {
        queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })
}

export function useDeleteFoodEntry(date: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (entryId: number) =>
      api.delete<{ success: boolean }>(`/api/nutrition/entries/${entryId}`),
    onSuccess: () => {
      for (const key of nutritionKeysFor(date)) {
        queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })
}

export function useRecipes() {
  return useQuery({
    queryKey: queryKeys.recipes,
    queryFn: () => api.get<RecipesResponse>('/api/recipes'),
  })
}

/**
 * Saving a recipe changes the macros of every meal already logged with it, so
 * this invalidates the nutrition keys as broadly as a meal edit would.
 */
export function useSaveRecipe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Recipe> & { id?: number }) =>
      id
        ? api.put<Recipe>(`/api/recipes/${id}`, body)
        : api.post<Recipe>('/api/recipes', body),
    onSuccess: () => {
      for (const key of [queryKeys.recipes, ['foods'], ['nutrition'],
        queryKeys.home, ['attributes']]) {
        queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })
}

export function useDeleteRecipe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (recipeId: number) =>
      api.delete<{ success: boolean }>(`/api/recipes/${recipeId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.recipes })
      queryClient.invalidateQueries({ queryKey: ['foods'] })
    },
  })
}

export function useLifestyleSummary() {
  return useQuery({
    queryKey: queryKeys.lifestyle,
    queryFn: () => api.get<LifestyleSummary>('/api/lifestyle'),
  })
}

export function useLifestyleDay(date: string) {
  return useQuery({
    queryKey: queryKeys.lifestyleDay(date),
    queryFn: () => api.get<LifestyleDayResponse>(`/api/lifestyle/${date}`),
  })
}

export function useSaveLifestyle(date: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<LifestyleDay>) =>
      api.put<LifestyleDayResponse>(`/api/lifestyle/${date}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['journal'] })
      for (const key of nutritionKeysFor(date)) {
        queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })
}

export function useLogSleep() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<SleepEntry> & { date: string }) =>
      api.post<{ success: boolean }>('/api/sleep', body),
    onSuccess: (_result, variables) => {
      for (const key of nutritionKeysFor(variables.date)) {
        queryClient.invalidateQueries({ queryKey: key })
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.sleep })
    },
  })
}

export function useProfile() {
  return useQuery({
    queryKey: queryKeys.profile,
    queryFn: () => api.get<ProfileResponse>('/api/profile'),
  })
}

/** Targets feed the adherence signal, so editing them rescores history. */
export function useSaveProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<UserProfile>) =>
      api.put<ProfileResponse>('/api/profile', body),
    onSuccess: () => {
      for (const key of [queryKeys.profile, ['nutrition'], queryKeys.lifestyle,
        queryKeys.home, ['attributes']]) {
        queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })
}

/* --- R5: learning --------------------------------------------------------- */

/**
 * Logging a study session moves Knowledge and Focus, so every mutation here
 * invalidates `home` and `attributes` alongside its own keys. Editing an area or
 * topic does not touch a score, so those invalidate narrowly.
 */
const LEARNING_SCORE_KEYS = [
  queryKeys.learning,
  queryKeys.learningSessions,
  queryKeys.home,
  ['attributes'],
]

export function useLearningSummary() {
  return useQuery({
    queryKey: queryKeys.learning,
    queryFn: () => api.get<LearningSummary>('/api/learning'),
  })
}

export function useLearningAreas() {
  return useQuery({
    queryKey: queryKeys.learningAreas,
    queryFn: () => api.get<LearningAreasResponse>('/api/learning/areas'),
  })
}

export function useLearningTopics() {
  return useQuery({
    queryKey: queryKeys.learningTopics,
    queryFn: () => api.get<LearningTopicsResponse>('/api/learning/topics'),
  })
}

export function useLearningSessions(limit?: number) {
  return useQuery({
    queryKey: queryKeys.learningSessions,
    queryFn: () =>
      api.get<LearningSessionsResponse>(
        `/api/learning/sessions${limit ? `?limit=${limit}` : ''}`,
      ),
  })
}

export function useSaveArea() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<LearningArea> & { id?: number }) =>
      id
        ? api.put<LearningArea>(`/api/learning/areas/${id}`, body)
        : api.post<LearningArea>('/api/learning/areas', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.learningAreas })
      // Topics carry their area's name and accent, so renaming an area or
      // recolouring it has to refresh them too.
      queryClient.invalidateQueries({ queryKey: queryKeys.learningTopics })
      queryClient.invalidateQueries({ queryKey: queryKeys.learning })
    },
  })
}

export function useDeleteArea() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (areaId: number) =>
      api.delete<{ success: boolean }>(`/api/learning/areas/${areaId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.learningAreas })
      queryClient.invalidateQueries({ queryKey: queryKeys.learningTopics })
    },
  })
}

export function useSaveTopic() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<LearningTopic> & { id?: number }) =>
      id
        ? api.put<LearningTopic>(`/api/learning/topics/${id}`, body)
        : api.post<LearningTopic>('/api/learning/topics', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.learningTopics })
      queryClient.invalidateQueries({ queryKey: queryKeys.learningAreas })
      queryClient.invalidateQueries({ queryKey: queryKeys.learning })
    },
  })
}

export function useDeleteTopic() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (topicId: number) =>
      api.delete<{ success: boolean }>(`/api/learning/topics/${topicId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.learningTopics })
      queryClient.invalidateQueries({ queryKey: queryKeys.learningAreas })
    },
  })
}

export function useLogSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<LearningSession> & { date: string }) =>
      api.post<LearningSession>('/api/learning/sessions', body),
    onSuccess: () => {
      for (const key of LEARNING_SCORE_KEYS) {
        queryClient.invalidateQueries({ queryKey: key })
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.learningTopics })
    },
  })
}

export function useDeleteSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: number) =>
      api.delete<{ success: boolean }>(`/api/learning/sessions/${sessionId}`),
    onSuccess: () => {
      for (const key of LEARNING_SCORE_KEYS) {
        queryClient.invalidateQueries({ queryKey: key })
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.learningTopics })
    },
  })
}

/* --- R6: habits, goals and tasks ------------------------------------------ */

/**
 * Nothing here invalidates `attributes` or `home`, and that is deliberate rather
 * than an oversight: goals and tasks do not move a score. Habit edits do not
 * either - changing a schedule changes what is expected, not what you did.
 *
 * The one exception is the paths/checklist surface, which habit edits DO affect,
 * because a habit is a checklist item under a different name.
 */
const GOAL_KEYS = [queryKeys.goals, queryKeys.goalsSummary, queryKeys.tasks]

export function useGoalsSummary() {
  return useQuery({
    queryKey: queryKeys.goalsSummary,
    queryFn: () => api.get<GoalsSummary>('/api/goals/summary'),
  })
}

export function useGoals(status?: GoalStatus) {
  return useQuery({
    queryKey: [...queryKeys.goals, status ?? 'all'],
    queryFn: () =>
      api.get<GoalsResponse>(`/api/goals${status ? `?status=${status}` : ''}`),
  })
}

export function useSaveGoal() {
  const queryClient = useQueryClient()
  return useMutation({
    // `milestones` is omitted from Partial<Goal> before being re-added as
    // strings: creating a goal takes a list of titles, while a stored goal
    // carries full Milestone objects, and an intersection cannot narrow the
    // field to the looser type.
    mutationFn: (
      { id, ...body }: Omit<Partial<Goal>, 'milestones'> & {
        id?: number
        milestones?: string[]
      },
    ) =>
      id
        ? api.put<Goal>(`/api/goals/${id}`, body)
        : api.post<Goal>('/api/goals', body),
    onSuccess: () => {
      for (const key of GOAL_KEYS) queryClient.invalidateQueries({ queryKey: key })
    },
  })
}

export function useDeleteGoal() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (goalId: number) =>
      api.delete<{ success: boolean }>(`/api/goals/${goalId}`),
    onSuccess: () => {
      for (const key of GOAL_KEYS) queryClient.invalidateQueries({ queryKey: key })
    },
  })
}

export function useAddMilestone(goalId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { title: string; target_date?: string | null }) =>
      api.post<Milestone>(`/api/goals/${goalId}/milestones`, body),
    onSuccess: () => {
      for (const key of GOAL_KEYS) queryClient.invalidateQueries({ queryKey: key })
    },
  })
}

export function useUpdateMilestone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; completed?: boolean; title?: string }) =>
      api.put<{ success: boolean }>(`/api/milestones/${id}`, body),
    onSuccess: () => {
      for (const key of GOAL_KEYS) queryClient.invalidateQueries({ queryKey: key })
    },
  })
}

export function useDeleteMilestone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (milestoneId: number) =>
      api.delete<{ success: boolean }>(`/api/milestones/${milestoneId}`),
    onSuccess: () => {
      for (const key of GOAL_KEYS) queryClient.invalidateQueries({ queryKey: key })
    },
  })
}

export function useTasks() {
  return useQuery({
    queryKey: queryKeys.tasks,
    queryFn: () => api.get<TasksResponse>('/api/tasks'),
  })
}

export function useSaveTask() {
  const queryClient = useQueryClient()
  return useMutation({
    // Creating returns the task, updating returns {success}. Neither caller uses
    // the result, but the union has to be stated or the two branches do not
    // agree on a type.
    mutationFn: (
      { id, ...body }: Partial<Task> & { id?: number; completed?: boolean },
    ): Promise<Task | { success: boolean }> =>
      id
        ? api.put<{ success: boolean }>(`/api/tasks/${id}`, body)
        : api.post<Task>('/api/tasks', body),
    onSuccess: () => {
      for (const key of GOAL_KEYS) queryClient.invalidateQueries({ queryKey: key })
    },
  })
}

export function useDeleteTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (taskId: number) =>
      api.delete<{ success: boolean }>(`/api/tasks/${taskId}`),
    onSuccess: () => {
      for (const key of GOAL_KEYS) queryClient.invalidateQueries({ queryKey: key })
    },
  })
}

export function useHabits(days?: number) {
  return useQuery({
    queryKey: queryKeys.habits(days),
    queryFn: () => api.get<HabitsResponse>(`/api/habits${days ? `?days=${days}` : ''}`),
  })
}

/**
 * A habit IS a checklist item under another name, so editing one invalidates the
 * paths and checklist keys that Today renders from.
 */
export function useUpdateHabit() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: {
      id: number
      name?: string
      weight?: number
      schedule_type?: ScheduleType
      schedule_days?: number[]
      target_per_week?: number | null
    }) => api.put<HabitStat>(`/api/habits/${id}`, body),
    onSuccess: () => {
      for (const key of [
        ['habits'], queryKeys.goalsSummary, queryKeys.goals,
        queryKeys.paths, queryKeys.checklistItems,
      ]) {
        queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })
}

/* --- R7: the XP ledger ---------------------------------------------------- */

export function useXpLedger(limit?: number) {
  return useQuery({
    queryKey: queryKeys.xpLedger,
    queryFn: () =>
      api.get<XpLedger>(`/api/gamification/ledger${limit ? `?limit=${limit}` : ''}`),
  })
}

/* --- R8: analytics -------------------------------------------------------- */

export function useAnalytics(period: AnalyticsPeriod) {
  return useQuery({
    queryKey: queryKeys.analytics(period),
    queryFn: () => api.get<AnalyticsResponse>(`/api/analytics?period=${period}`),
    // Keep the previous period's data on screen while the next one loads, so
    // switching from 30 to 90 days redraws rather than collapsing to skeletons.
    placeholderData: (previous) => previous,
  })
}

/* --- R9: onboarding ------------------------------------------------------- */

export function useOnboarding() {
  return useQuery({
    queryKey: queryKeys.onboarding,
    queryFn: () => api.get<OnboardingState>('/api/onboarding'),
  })
}

export function useSaveOnboarding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      answers?: Partial<OnboardingAnswers>
      step?: number
      complete?: boolean
    }) => api.put<OnboardingState>('/api/onboarding', body),
    onSuccess: (state) => {
      queryClient.setQueryData(queryKeys.onboarding, state)
      // Targets are denominators the engine scores against, so saving one
      // re-judges history - every page showing a score is now stale.
      queryClient.invalidateQueries({ queryKey: queryKeys.home })
      queryClient.invalidateQueries({ queryKey: queryKeys.profile })
      queryClient.invalidateQueries({ queryKey: queryKeys.attributes() })
    },
  })
}

export function useOnboardingPrompt() {
  const queryClient = useQueryClient()
  const update = (path: string) => async () => {
    const state = await api.post<OnboardingState>(path, {})
    queryClient.setQueryData(queryKeys.onboarding, state)
    return state
  }
  return {
    dismiss: useMutation({ mutationFn: update('/api/onboarding/dismiss') }),
    reopen: useMutation({ mutationFn: update('/api/onboarding/reopen') }),
  }
}
