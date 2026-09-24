import { useState } from 'react'
import { ArrowLeft, Dumbbell, Search } from 'lucide-react'
import { Link } from 'react-router'

import { useExercises } from '../api/queries'
import { PageHeader } from '../components/layout/PageHeader'
import { ExerciseDemonstration } from '../components/training/ExerciseDemonstration'
import { PersonalBook, type BookPage } from '../components/ui/PersonalBook'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { SkeletonGrid } from '../components/ui/Skeleton'

export function ExerciseBook() {
  const exercises = useExercises()
  const [active, setActive] = useState('cover')
  const [search, setSearch] = useState('')
  return <>
    <PageHeader title="Exercise book" storyKind="training" description="A field guide to movement. Open a chapter, find your exercise, and follow the demonstration."
      icon={Dumbbell} accent="fitness" actions={<Link to="/training" className="flex items-center gap-2 text-meta text-ink-muted"><ArrowLeft size={16} /> Training</Link>} />
    <QueryBoundary query={exercises} loading={<SkeletonGrid />}>{(data) => {
      const sorted = [...data.exercises].sort((first, second) => first.primary_muscle.localeCompare(second.primary_muscle) || first.name.localeCompare(second.name))
      const chapters = [...new Set(sorted.map((exercise) => exercise.primary_muscle))]
      const pages: BookPage[] = sorted.map((exercise) => ({
        id: `exercise-${exercise.id}`, title: exercise.name, chapter: exercise.primary_muscle.replaceAll('-', ' '),
        content: <>
          <ExerciseDemonstration exercise={exercise} />
          <p className="my-3 text-xs capitalize">{exercise.equipment} · {exercise.difficulty}</p>
          <ol className="book-list">{exercise.instructions.map((step, index) => <li key={index}><span>{index + 1}.</span><span>{step}</span></li>)}</ol>
          <p className="book-note">Primary: {exercise.primary_muscle.replaceAll('-', ' ')}{exercise.secondary_muscles.length ? `. Also works ${exercise.secondary_muscles.join(', ')}.` : '.'}</p>
        </>,
      }))
      return <>
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-3">
          <label className="flex flex-1 items-center gap-2 rounded-lg border border-line px-3 py-2 text-ink-muted"><Search size={16} />
            <input aria-label="Find an exercise in the book" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a movement…" className="min-w-0 flex-1 bg-transparent text-label outline-none" />
          </label>
          <select aria-label="Jump to muscle chapter" value="" onChange={(event) => setActive(`exercise-${sorted.find((exercise) => exercise.primary_muscle === event.target.value)?.id}`)} className="rounded-lg border border-line bg-surface-card p-2 text-label text-ink">
            <option value="" disabled>Jump to chapter</option>{chapters.map((chapter) => <option key={chapter} value={chapter}>{chapter.replaceAll('-', ' ')}</option>)}
          </select>
        </div>
        {search && <div className="mx-auto mt-2 flex max-h-48 max-w-5xl flex-wrap gap-2 overflow-auto" role="region" aria-label="Exercise search results">
          {sorted.filter((exercise) => `${exercise.name} ${exercise.primary_muscle} ${exercise.equipment}`.toLowerCase().includes(search.toLowerCase())).map((exercise) => <button key={exercise.id} type="button" onClick={() => { setActive(`exercise-${exercise.id}`); setSearch('') }} className="rounded-md border border-line px-3 py-2 text-meta text-ink-muted">{exercise.name}</button>)}
        </div>}
        <PersonalBook title="The art of movement" subtitle={`${sorted.length} exercises. A little knowledge for every session.`} kind="exercise" pages={pages} activeId={active} onPageChange={setActive} />
      </>
    }}</QueryBoundary>
  </>
}
