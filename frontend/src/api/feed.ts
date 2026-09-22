import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { FeedPostsResponse, WeeklyPost } from './types'

export function useFeedPosts() {
  return useQuery({ queryKey: ['feed', 'posts'], queryFn: () => api.get<FeedPostsResponse>('/api/feed/posts') })
}

export function useWriteWeeklyPost() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { end: string; refresh?: boolean }) => api.post<WeeklyPost>('/api/feed/posts', body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['feed', 'posts'] }),
  })
}
