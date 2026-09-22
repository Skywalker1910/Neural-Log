import { ChevronLeft, ChevronRight } from 'lucide-react'
import { AnimatePresence, m } from 'motion/react'
import { useState, type ReactNode } from 'react'

import { Button } from './Button'
import { cn } from '../../lib/cn'

/** A shared, accessible page-turn treatment for personal reference collections. */
export function PersonalBook({
  title,
  subtitle,
  pages,
  accent = 'brand',
}: {
  title: string
  subtitle?: string
  pages: { title: string; content: ReactNode }[]
  accent?: 'brand' | 'fitness' | 'lifestyle' | 'goals' | 'learning'
}) {
  const [page, setPage] = useState(0)
  const tone = {
    brand: 'border-brand/40 from-brand-muted', fitness: 'border-fitness/40 from-fitness/15',
    lifestyle: 'border-lifestyle/40 from-lifestyle/15', goals: 'border-goals/40 from-goals/15',
    learning: 'border-learning/40 from-learning/15',
  }[accent]
  const current = pages[page]

  return (
    <section className="mx-auto w-full max-w-3xl [perspective:1800px]">
      <div className={cn('relative overflow-hidden rounded-xl border bg-gradient-to-br via-surface-card to-surface-base shadow-overlay', tone)}>
        <div className="absolute inset-y-0 left-1/2 w-px bg-white/10" aria-hidden />
        <div className="min-h-[26rem] p-6 sm:p-9">
          <p className="text-caption uppercase tracking-[0.2em] text-ink-subtle">{subtitle ?? 'Personal collection'}</p>
          <h2 className="mt-2 text-heading text-ink">{title}</h2>
          <AnimatePresence mode="wait" initial={false}>
            <m.div
              key={page}
              initial={{ opacity: 0, rotateY: page ? 18 : -18, x: page ? 20 : -20 }}
              animate={{ opacity: 1, rotateY: 0, x: 0 }}
              exit={{ opacity: 0, rotateY: page ? -18 : 18, x: page ? -20 : 20 }}
              transition={{ type: 'spring', stiffness: 260, damping: 28 }}
              className="mt-7"
            >
              <p className="text-caption uppercase tracking-[0.16em] text-ink-subtle">{current.title}</p>
              <div className="mt-3 text-label text-ink">{current.content}</div>
            </m.div>
          </AnimatePresence>
        </div>
        <footer className="flex items-center justify-between border-t border-white/10 px-4 py-3">
          <Button size="sm" variant="ghost" icon={ChevronLeft} disabled={page === 0}
                  onClick={() => setPage((value) => value - 1)}>Previous</Button>
          <span className="tabular text-meta text-ink-subtle">{page + 1} / {pages.length}</span>
          <Button size="sm" variant="ghost" icon={ChevronRight} disabled={page === pages.length - 1}
                  onClick={() => setPage((value) => value + 1)}>Next</Button>
        </footer>
      </div>
    </section>
  )
}
