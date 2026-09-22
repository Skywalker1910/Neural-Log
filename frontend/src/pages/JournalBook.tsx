import { useState } from 'react'
import { BookOpenText, Sparkles } from 'lucide-react'

import { api } from '../api/client'
import { useAssistantState, useLifestyleDay, useSaveLifestyle } from '../api/queries'
import { PageHeader } from '../components/layout/PageHeader'
import { Button } from '../components/ui/Button'
import { PersonalBook } from '../components/ui/PersonalBook'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { todayISO } from '../lib/date'

export function JournalBook() {
  const [date, setDate] = useState(todayISO)
  const day = useLifestyleDay(date)
  const assistant = useAssistantState()
  const save = useSaveLifestyle(date)
  const [draft, setDraft] = useState<string | null>(null)
  const [summarising, setSummarising] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function summarise() {
    setSummarising(true); setError(null)
    try {
      const response = await api.post<{ summary: string }>('/api/journal/summary', { date })
      setDraft(response.summary)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not summarise this day.')
    } finally { setSummarising(false) }
  }

  return <>
    <PageHeader title="Journal" description="A dated personal record, with an optional AI draft built only from what you logged." icon={BookOpenText} accent="goals" actions={<input type="date" value={date} onChange={(event) => { setDate(event.target.value); setDraft(null) }} className="rounded-md border border-line bg-surface-card px-2 py-1.5 text-meta text-ink" />} />
    <QueryBoundary query={day} loading={<SkeletonGrid />}>{(data) => {
      const text = draft ?? data.lifestyle?.journal ?? ''
      return <div className="flex flex-col gap-4"><PersonalBook title={date} subtitle="Private daily journal" accent="goals" pages={[
        { title: 'Reflection', content: <textarea value={text} onChange={(event) => setDraft(event.target.value)} rows={11} placeholder="Write about your day." className="min-h-56 w-full resize-y bg-transparent text-label leading-7 text-ink outline-none placeholder:text-ink-subtle" /> },
        { title: 'What was logged', content: <ul className="space-y-2 text-ink-muted"><li>Sleep: {data.sleep ? `${Math.floor(data.sleep.duration_minutes / 60)}h ${data.sleep.duration_minutes % 60}m` : 'not logged'}</li><li>Steps: {data.lifestyle?.steps?.toLocaleString() ?? 'not logged'}</li><li>Water: {data.lifestyle?.water_ml ? `${data.lifestyle.water_ml} ml` : 'not logged'}</li><li>Mood: {data.lifestyle?.mood ?? 'not logged'} / 5</li></ul> },
      ]} />
        <div className="flex flex-wrap items-center justify-center gap-2"><Button variant="primary" loading={save.isPending} onClick={() => save.mutate({ journal: text })}>Save journal</Button>{assistant.data?.configured && <Button variant="secondary" icon={Sparkles} loading={summarising} onClick={() => void summarise()}>Draft from my log</Button>}</div>
        {error && <p className="text-center text-label text-danger">{error}</p>}
      </div>
    }}</QueryBoundary>
  </>
}
