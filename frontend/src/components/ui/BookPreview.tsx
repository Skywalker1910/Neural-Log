import { lazy, Suspense, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ArrowUpRight, X } from 'lucide-react'

import { BookCover } from './BookCover'
import { SkeletonGrid } from './Skeleton'
import './personalBook.css'

const ExerciseBook = lazy(() => import('../../pages/ExerciseBook').then((module) => ({ default: module.ExerciseBook })))
const RecipeBook = lazy(() => import('../../pages/RecipeBook').then((module) => ({ default: module.RecipeBook })))
const JournalBook = lazy(() => import('../../pages/JournalBook').then((module) => ({ default: module.JournalBook })))

export type BookKind = 'exercise' | 'recipe' | 'journal'

const COLLECTION = {
  exercise: { label: 'Exercise book', title: 'The art of movement', subtitle: 'A field guide to a stronger you.', component: ExerciseBook },
  recipe: { label: 'Recipe book', title: 'Made in my kitchen', subtitle: 'Favourite flavours. Your own recipes.', component: RecipeBook },
  journal: { label: 'Journal', title: 'Days worth keeping', subtitle: 'The small things. Your own words.', component: JournalBook },
}

export function BookPreview({ kind }: { kind: BookKind }) {
  const book = COLLECTION[kind]
  const Reader = book.component
  const dialog = useRef<HTMLDialogElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [visited, setVisited] = useState(false)
  const [origin, setOrigin] = useState({ x: 0, y: 0 })

  useEffect(() => {
    if (!open) return
    const reader = dialog.current
    const cover = trigger.current
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    reader?.showModal()
    return () => {
      reader?.close()
      document.body.style.overflow = previous
      cover?.focus({ preventScroll: true })
    }
  }, [open])

  return <>
    <button ref={trigger} type="button" className={`book-preview personal-book book-${kind}`} aria-label={`Open ${book.label}`} aria-haspopup="dialog" onClick={() => {
      const bounds = trigger.current?.getBoundingClientRect()
      if (bounds) setOrigin({ x: bounds.x + bounds.width / 2 - window.innerWidth / 2, y: bounds.y + bounds.height / 2 - window.innerHeight / 2 })
      setVisited(true)
      setOpen(true)
    }}>
      <div className="book-miniature"><BookCover kind={kind} title={book.title} subtitle={book.subtitle} /></div>
      <span className="book-preview-caption">{book.label}<ArrowUpRight size={15} aria-hidden /></span>
    </button>
    {visited && createPortal(<dialog ref={dialog} className="book-reader" aria-label={book.label}
      style={{ '--reader-x': `${origin.x}px`, '--reader-y': `${origin.y}px` } as CSSProperties}
      onKeyDownCapture={(event) => {
        if (event.key === 'Escape' && dialog.current?.querySelector('[role="dialog"]')) event.preventDefault()
      }}
      onClick={(event) => {
        if ((event.target as HTMLElement).closest('a[href^="/"]')) setOpen(false)
      }}
      onCancel={(event) => {
        event.preventDefault()
        if (!dialog.current?.querySelector('[role="dialog"]')) setOpen(false)
      }}>
      <div className="book-reader-bar"><span>Your personal collection</span><button type="button" onClick={() => setOpen(false)} aria-label="Close book"><X size={18} /> Close book</button></div>
      <div className="book-reader-content"><Suspense fallback={<SkeletonGrid />}><Reader /></Suspense></div>
    </dialog>, document.body)}
  </>
}

export function BookWorkspace({ kind, children }: { kind: BookKind; children: ReactNode }) {
  return <div className="book-workspace"><div className="min-w-0">{children}</div><BookPreview kind={kind} /></div>
}
