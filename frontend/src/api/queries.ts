import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type {
  AttributesResponse,
  ChecklistItemsResponse,
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
