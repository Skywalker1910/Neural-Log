import { useQuery } from '@tanstack/react-query'

import { api } from './client'
import type {
  AttributesResponse,
  CurrentUser,
  DayDetail,
  GamificationSummary,
  HomeSummary,
  Leaderboard,
  PathsResponse,
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
