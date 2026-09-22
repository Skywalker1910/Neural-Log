import { BookOpen, ChevronLeft, ChevronRight, List } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode } from 'react'

import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { BookCover } from './BookCover'
import './personalBook.css'

export interface BookPage {
  id: string
  title: string
  chapter: string
  content: ReactNode
}

interface Turn {
  target: number
  direction: number
  progress: number
  released: boolean
  commit: boolean
}

export function PersonalBook({ title, subtitle, pages, kind = 'journal', activeId, onPageChange }: {
  title: string
  subtitle: string
  pages: BookPage[]
  kind?: 'recipe' | 'exercise' | 'journal'
  activeId?: string
  onPageChange?: (id: string) => void
}) {
  const [selected, setSelected] = useState('cover')
  const [wide, setWide] = useState(false)
  const [turn, setTurn] = useState<Turn | null>(null)
  const stage = useRef<HTMLDivElement>(null)
  const gesture = useRef<{ pointer: number; x: number; y: number; started: number } | null>(null)
  const reduced = usePrefersReducedMotion()
  const indexCount = Math.max(1, Math.ceil(pages.length / 10))
  const indexPages = Array.from({ length: indexCount }, (_, index) => ({
    id: `contents-${index}`, title: index ? 'Contents, continued' : 'Contents', chapter: 'Find your page',
    content: <nav aria-label={`Contents ${index + 1}`} className="book-index">
      {pages.slice(index * 10, index * 10 + 10).map((entry, offset, group) => <div key={entry.id}>
        {(offset === 0 || group[offset - 1].chapter !== entry.chapter) && <h3>{entry.chapter}</h3>}
        <button type="button" onClick={() => navigate(entry.id)}>
          <span>{entry.title}</span><i /><span>{1 + indexCount + index * 10 + offset}</span>
        </button>
      </div>)}
      {pages.length === 0 && <p>Your first entry will begin this volume.</p>}
    </nav>,
  }))
  const leaves: BookPage[] = [
    { id: 'cover', title, chapter: subtitle, content: <BookCover kind={kind} title={title} subtitle={subtitle} /> },
    ...indexPages, ...pages,
  ]
  const requestedId = activeId ?? selected
  const found = leaves.findIndex((entry) => entry.id === requestedId)
  const page = Math.max(0, found)
  const spread = wide && page > 0 ? page - (page % 2 === 0 ? 1 : 0) : page
  const last = wide ? leaves.length - (leaves.length % 2 === 0 ? 1 : 2) : leaves.length - 1

  useEffect(() => {
    if (!stage.current) return
    const observer = new ResizeObserver(([entry]) => setWide(entry.contentRect.width >= 720))
    observer.observe(stage.current)
    return () => observer.disconnect()
  }, [])

  const targetId = turn ? leaves[turn.target]?.id : undefined
  useEffect(() => {
    if (!turn?.released || !targetId) return
    const timeout = window.setTimeout(() => {
      if (turn.commit) {
        setSelected(targetId)
        onPageChange?.(targetId)
      }
      setTurn(null)
    }, reduced ? 0 : 430)
    return () => window.clearTimeout(timeout)
  }, [turn, targetId, onPageChange, reduced])

  function navigate(id: string) {
    if (turn) return
    setSelected(id)
    onPageChange?.(id)
  }

  function targetFor(direction: number) {
    if (direction > 0) return spread === 0 ? 1 : Math.min(last, spread + (wide ? 2 : 1))
    return Math.max(0, spread - (wide ? 2 : 1))
  }

  function flip(direction: number) {
    const target = targetFor(direction)
    if (turn || target === spread) return
    setTurn({ target, direction, progress: 0, released: false, commit: false })
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      setTurn({ target, direction, progress: 1, released: true, commit: true })
    }))
  }

  function pointerDown(event: PointerEvent<HTMLDivElement>) {
    if (turn || !event.isPrimary || event.button !== 0 ||
        (event.target as HTMLElement).closest('button,a,input,textarea,select,[data-no-turn]')) return
    gesture.current = { pointer: event.pointerId, x: event.clientX, y: event.clientY, started: event.timeStamp }
  }

  function pointerMove(event: PointerEvent<HTMLDivElement>) {
    const start = gesture.current
    if (!start || start.pointer !== event.pointerId || turn?.released) return
    const distance = event.clientX - start.x
    if (!turn && Math.abs(event.clientY - start.y) > Math.abs(distance)) {
      gesture.current = null
      return
    }
    if (Math.abs(distance) < 8 && !turn) return
    const direction = turn?.direction ?? (distance < 0 ? 1 : -1)
    const target = targetFor(direction)
    if (target === spread) return
    event.currentTarget.setPointerCapture(event.pointerId)
    const width = event.currentTarget.clientWidth / (wide ? 2 : 1)
    const progress = Math.min(0.99, Math.max(0, -distance * direction / width))
    setTurn({ target, direction, progress, released: false, commit: false })
  }

  function pointerUp(event: PointerEvent<HTMLDivElement>, cancelled = false) {
    const start = gesture.current
    gesture.current = null
    if (!turn || turn.released) return
    const quick = start && event.timeStamp - start.started < 350 && Math.abs(event.clientX - start.x) > 35
    const commit = !cancelled && (turn.progress > 0.22 || Boolean(quick))
    setTurn({ ...turn, progress: commit ? 1 : 0, released: true, commit })
  }

  function leaf(index: number | null, side: string, hidden = false) {
    const entry = index === null ? undefined : leaves[index]
    return <div className={`book-paper ${side} ${entry?.id === 'cover' ? 'book-cover-paper' : ''}`} inert={hidden || !entry} aria-hidden={hidden || !entry || undefined}>
      {entry && (entry.id === 'cover' ? entry.content : <>
        <header><span>{entry.chapter}</span><h2>{entry.title}</h2></header>
        <div className="book-paper-content">{entry.content}</div>
        <footer><span>{title}</span><span>{index}</span></footer>
      </>)}
    </div>
  }

  const left = spread === 0 ? null : spread
  const right = spread === 0 ? 0 : spread + 1
  const target = turn?.target ?? spread
  const forward = (turn?.direction ?? 1) > 0
  const targetLeft = target === 0 ? null : target
  const targetRight = target === 0 ? 0 : target + 1
  const coverOffset = wide ? (spread === 0 ? 1 - (turn?.progress ?? 0) : target === 0 ? turn?.progress ?? 0 : 0) : 0

  return <section className={`personal-book book-${kind}`} aria-label={title}>
    <div className="book-toolbar">
      <button type="button" disabled={Boolean(turn)} onClick={() => navigate('cover')}><BookOpen size={15} /> Cover</button>
      <button type="button" disabled={Boolean(turn)} onClick={() => navigate('contents-0')}><List size={15} /> Index</button>
      <span>Drag a page · swipe to turn</span>
    </div>
    <div ref={stage} className="book-stage">
      <div className={`book-spread ${wide ? 'book-wide' : 'book-single'} ${spread === 0 && !turn ? 'book-closed' : ''} ${turn?.released ? 'book-positioning' : ''}`}
        style={{ transform: `translateX(${-25 * coverOffset}%)` }}
        tabIndex={0} role="group" aria-label="Book pages" onPointerDown={pointerDown} onPointerMove={pointerMove}
        onPointerUp={pointerUp} onPointerCancel={(event) => pointerUp(event, true)}
        onKeyDown={(event) => {
          if ((event.target as HTMLElement).closest('input,textarea,select,button,a')) return
          if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
            event.preventDefault()
            flip(event.key === 'ArrowRight' ? 1 : -1)
          }
        }}>
        {wide ? <>
          {leaf(turn && !forward ? targetLeft : left, 'book-left', Boolean(turn))}
          {leaf(turn && forward ? targetRight : right, 'book-right', Boolean(turn))}
        </> : leaf(turn ? target : spread, 'book-right', Boolean(turn))}
        {turn && <div className={`book-turning ${forward ? 'book-forward' : 'book-backward'} ${turn.released ? 'book-settling' : ''}`}
          aria-hidden inert style={{ '--turn': `${turn.progress * (forward ? -180 : 180)}deg`, '--shade': Math.sin(turn.progress * Math.PI) * 0.3 } as CSSProperties}>
          <div className="book-face book-front">{leaf(wide ? (forward ? right : left) : spread, '', true)}</div>
          <div className="book-face book-back">{leaf(wide ? (forward ? targetLeft : targetRight) : target, '', true)}</div>
        </div>}
      </div>
    </div>
    <div className="book-controls">
      <button type="button" aria-label="Previous pages" disabled={spread === 0 || Boolean(turn)} onClick={() => flip(-1)}><ChevronLeft size={18} /> Previous</button>
      <span aria-live="polite">{page === 0 ? 'Cover' : `Page ${spread}${wide && spread + 1 < leaves.length ? `–${spread + 1}` : ''} of ${leaves.length - 1}`}</span>
      <button type="button" aria-label="Next pages" disabled={spread >= last || Boolean(turn)} onClick={() => flip(1)}>Next <ChevronRight size={18} /></button>
    </div>
  </section>
}
