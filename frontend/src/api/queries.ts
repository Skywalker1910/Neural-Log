import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type {
  AttributesResponse,
  ChecklistItemsResponse,
  ExerciseHistory,
  ExercisesResponse,
  LoggedSet,
  Routine,
  RoutinesResponse,
  TrainingSummary,
  Workout,
  CurrentUser,
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
}

export function useCurrentUser() {
  return useQuery({
    queryKey: queryKeys.currentUser,
    queryFn: () => api.get<CurrentUser>('/api/current-user'),
    staleTime: 5 * 60_000,
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
