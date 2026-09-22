import { useState } from 'react'
import { Dumbbell } from 'lucide-react'

import { useExercises } from '../api/queries'
import { PageHeader } from '../components/layout/PageHeader'
import { PersonalBook } from '../components/ui/PersonalBook'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { SkeletonGrid } from '../components/ui/Skeleton'

export function ExerciseBook() {
  const exercises = useExercises()
  const [selected, setSelected] = useState<number | null>(null)
  return <><PageHeader title="Exercise book" description="Movement cues and instructions, laid out for a quiet read before training." icon={Dumbbell} accent="fitness" />
    <QueryBoundary query={exercises} loading={<SkeletonGrid />}>{(data) => {
      const exercise = data.exercises.find((item) => item.id === selected) ?? data.exercises[0]
      if (!exercise) return null
      return <div className="grid gap-4 lg:grid-cols-[13rem_1fr]"><aside className="flex max-h-[34rem] gap-2 overflow-auto lg:flex-col">{data.exercises.slice(0, 30).map((item) => <button key={item.id} type="button" onClick={() => setSelected(item.id)} className={`shrink-0 rounded-lg border px-3 py-2 text-left text-meta ${item.id === exercise.id ? 'border-fitness bg-fitness/15 text-ink' : 'border-line text-ink-muted'}`}>{item.name}</button>)}</aside>
        <PersonalBook title={exercise.name} subtitle={`${exercise.primary_muscle} · ${exercise.category}`} accent="fitness" pages={[
          { title: 'Setup', content: <p>{exercise.equipment || 'No equipment required'} · {exercise.difficulty || 'all levels'}</p> },
          { title: 'How to move', content: <ol className="space-y-3">{exercise.instructions.map((step, index) => <li key={index} className="flex gap-3"><span className="tabular text-fitness">{index + 1}</span><span>{step}</span></li>)}</ol> },
          { title: 'Targets', content: <p>Primary: {exercise.primary_muscle}. {exercise.secondary_muscles.length ? `Also works ${exercise.secondary_muscles.join(', ')}.` : 'Keep the movement controlled and stop for pain.'}</p> },
        ]} />
      </div>
    }}</QueryBoundary>
  </>
}
