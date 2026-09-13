import type { ReactNode } from 'react'

import { cn } from '../../lib/cn'

export interface Column<T> {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  align?: 'left' | 'right'
  /** Hide on narrow screens rather than letting the table overflow awkwardly. */
  hideBelow?: 'sm' | 'md'
}

interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  /** Highlighted row - e.g. the signed-in user in a leaderboard. */
  isHighlighted?: (row: T) => boolean
  empty?: ReactNode
  caption?: string
}

const HIDE_BELOW = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  isHighlighted,
  empty,
  caption,
}: DataTableProps<T>) {
  if (rows.length === 0 && empty) return <>{empty}</>

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-line">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn(
                  'px-3 py-2.5 text-caption font-medium uppercase tracking-wider text-ink-subtle',
                  column.align === 'right' ? 'text-right' : 'text-left',
                  column.hideBelow && HIDE_BELOW[column.hideBelow],
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={cn(
                'border-b border-line/60 last:border-0',
                isHighlighted?.(row) && 'bg-brand/8',
              )}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cn(
                    'px-3 py-3 text-label text-ink',
                    column.align === 'right' ? 'tabular text-right' : 'text-left',
                    column.hideBelow && HIDE_BELOW[column.hideBelow],
                  )}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
