import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { TriangleAlert } from 'lucide-react'

import { Button } from './Button'
import { EmptyState } from './EmptyState'
import { SkeletonGrid } from './Skeleton'

interface QueryBoundaryProps<T> {
  query: UseQueryResult<T>
  /** Shown while the first fetch is in flight. */
  loading?: ReactNode
  /** Lets a section declare what "no data yet" means for its own shape. */
  isEmpty?: (data: T) => boolean
  empty?: ReactNode
  children: (data: T) => ReactNode
}

/**
 * Every data-backed section renders through this, so loading / error / empty /
 * retry are handled once rather than forgotten per component (brief §52).
 */
export function QueryBoundary<T>({ query, loading, isEmpty, empty, children }: QueryBoundaryProps<T>) {
  if (query.isPending) {
    return <>{loading ?? <SkeletonGrid />}</>
  }

  if (query.isError) {
    return (
      <EmptyState
        icon={TriangleAlert}
        title="Couldn't load this"
        description={query.error instanceof Error ? query.error.message : 'Something went wrong.'}
        action={
          <Button variant="secondary" onClick={() => void query.refetch()} loading={query.isFetching}>
            Try again
          </Button>
        }
      />
    )
  }

  if (isEmpty?.(query.data) && empty) {
    return <>{empty}</>
  }

  return <>{children(query.data)}</>
}
