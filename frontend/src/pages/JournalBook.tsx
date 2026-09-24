import { useState } from 'react'
import { BookOpenText, Sparkles } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import { useAssistantState, useLifestyleDay, useSaveLifestyle } from '../api/queries'
import { PageHeader } from '../components/layout/PageHeader'
import { Button } from '../components/ui/Button'
import { PersonalBook, type BookPage } from '../components/ui/PersonalBook'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { todayISO } from '../lib/date'

function JournalEditor({ date, draft, onDraft }: { date: string; draft?: string; onDraft: (text: string) => void }) {
  const day = useLifestyleDay(date)
  const assistant = useAssistantState()
  const save = useSaveLifestyle(date)
  const [summarising, setSummarising] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function summarise() {
    setSummarising(true)
    setError(null)
    try {
      const response = await api.post<{ summary: string }>('/api/journal/summary', { date })
      onDraft(response.summary)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not summarise this day.')
    } finally { setSummarising(false) }
  }
  return <QueryBoundary query={day} loading={<p>Opening your entry…</p>}>{(data) => <div data-no-turn>
    <textarea aria-label={`Journal for ${date}`} value={draft ?? data.lifestyle?.journal ?? ''} onChange={(event) => { onDraft(event.target.value); save.reset() }} rows={11} placeholder="What would you like to remember?" className="w-full resize-y bg-transparent font-serif text-base leading-8 outline-none" />
    <div className="mt-4 flex flex-wrap gap-2">
      <Button variant="primary" loading={save.isPending} disabled={summarising} onClick={() => save.mutate({ journal: draft ?? data.lifestyle?.journal ?? '' })}>Save entry</Button>
      {assistant.data?.configured && <button className="book-link" type="button" disabled={summarising || save.isPending} onClick={() => void summarise()}><Sparkles size={14} />{summarising ? 'Writing…' : 'Draft from my day'}</button>}
    </div>
    {save.isSuccess && <p role="status" className="mt-3">Entry saved.</p>}
    {(error || save.error) && <p role="alert" className="mt-3">{error ?? save.error?.message}</p>}
    <p className="mt-4 text-xs opacity-60">AI drafts use your recorded day. Review the words before saving them.</p>
  </div>}</QueryBoundary>
}

export function JournalBook() {
  const [date, setDate] = useState(todayISO)
  const [active, setActive] = useState('cover')
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const entries = useQuery({ queryKey: ['journal', 'entries'], queryFn: () => api.get<{ entries: { date: string; journal: string }[] }>('/api/journal/entries') })
  return <>
    <PageHeader title="Journal" storyKind="lifestyle" description="A place for the ordinary days, the milestones, and everything between." icon={BookOpenText} accent="goals"
      actions={<label className="flex items-center gap-2 text-meta text-ink-muted">Write for<input aria-label="Journal date" type="date" value={date} onChange={(event) => {
        if (event.target.value) { setDate(event.target.value); setActive(`day-${event.target.value}`) }
      }} className="rounded-md border border-line bg-surface-card px-2 py-1.5 text-ink" /></label>} />
    <QueryBoundary query={entries} loading={<SkeletonGrid />}>{(data) => {
      const dates = [...new Set([date, ...data.entries.map((entry) => entry.date)])].sort().reverse()
      const pages: BookPage[] = dates.map((entryDate) => ({ id: `day-${entryDate}`,
        title: new Date(`${entryDate}T12:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' }),
        chapter: new Date(`${entryDate}T12:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' }),
        content: <JournalEditor key={entryDate} date={entryDate} draft={drafts[entryDate]} onDraft={(text) => setDrafts((current) => ({ ...current, [entryDate]: text }))} />,
      }))
      return <PersonalBook title="Days worth keeping" subtitle="The small things. The big things. Your own words." kind="journal" pages={pages} activeId={active} onPageChange={setActive} />
    }}</QueryBoundary>
  </>
}
