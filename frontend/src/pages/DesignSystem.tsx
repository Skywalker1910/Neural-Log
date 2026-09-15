import { useState, type ReactNode } from 'react'
import { Dumbbell, Flame, GraduationCap, Moon, Droplets, Palette } from 'lucide-react'

import { AttributeRadar, TrendChart } from '../components/charts'
import { PageHeader } from '../components/layout/PageHeader'
import { ItemIcon } from '../components/ui/ItemIcon'
import { AttributeBadge } from '../components/ui/AttributeBadge'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ConfirmationDialog } from '../components/ui/ConfirmationDialog'
import { DataTable } from '../components/ui/DataTable'
import { EmptyState } from '../components/ui/EmptyState'
import { MetricCard } from '../components/ui/MetricCard'
import { Modal } from '../components/ui/Modal'
import { ProgressCard } from '../components/ui/ProgressCard'
import { SkeletonCard } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'

// Tailwind only generates classes it can see as literal strings, so these are
// spelled out rather than built with template literals.
const SURFACES: Array<[string, string]> = [
  ['surface-base', 'bg-surface-base'],
  ['surface-card', 'bg-surface-card'],
  ['surface-raised', 'bg-surface-raised'],
  ['surface-overlay', 'bg-surface-overlay'],
]

const CATEGORIES: Array<[string, string]> = [
  ['brand', 'bg-brand'],
  ['fitness', 'bg-fitness'],
  ['learning', 'bg-learning'],
  ['lifestyle', 'bg-lifestyle'],
  ['goals', 'bg-goals'],
  ['discipline', 'bg-discipline'],
  ['recovery', 'bg-recovery'],
]

const TYPE_SCALE = [
  { name: 'metric-xl', className: 'text-metric-xl', sample: '2,480' },
  { name: 'metric', className: 'text-metric', sample: '1,850' },
  { name: 'heading', className: 'text-heading', sample: 'Page heading' },
  { name: 'section', className: 'text-section', sample: 'Section heading' },
  { name: 'label', className: 'text-label', sample: 'Label / body text' },
  { name: 'meta', className: 'text-meta', sample: 'Metadata' },
  { name: 'caption', className: 'text-caption uppercase', sample: 'Caption' },
]

const RADAR_SAMPLE = [
  { attribute: 'Discipline', value: 78, previous: 64 },
  { attribute: 'Knowledge', value: 62, previous: 55 },
  { attribute: 'Strength', value: 71, previous: 68 },
  { attribute: 'Stamina', value: 54, previous: 49 },
  { attribute: 'Agility', value: 40, previous: 38 },
  { attribute: 'Recovery', value: 66, previous: 72 },
]

const TREND_SAMPLE = [
  { label: 'Mon', value: 72 },
  { label: 'Tue', value: 80 },
  { label: 'Wed', value: 64 },
  { label: 'Thu', value: 88 },
  { label: 'Fri', value: 91 },
  { label: 'Sat', value: 70 },
  { label: 'Sun', value: 84 },
]

interface SampleRow {
  rank: number
  name: string
  xp: number
}

const TABLE_SAMPLE: SampleRow[] = [
  { rank: 1, name: 'AdityaMore', xp: 2480 },
  { rank: 2, name: 'friend-two', xp: 1975 },
  { rank: 3, name: 'friend-three', xp: 1204 },
]

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="mb-3 text-section text-ink">{title}</h2>
      {children}
    </section>
  )
}

/**
 * Living reference for the design system. Not linked from the product nav - it
 * exists so the tokens and primitives can be eyeballed in one place.
 */
export function DesignSystem() {
  const [modalOpen, setModalOpen] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  return (
    <>
      <PageHeader
        title="Design system"
        description="Tokens and primitives every workspace is built from."
        icon={Palette}
        actions={<Badge tone="brand">Phase 1</Badge>}
      />

      <Section title="Surfaces">
        <div className="grid gap-3 sm:grid-cols-4">
          {SURFACES.map(([name, bgClass]) => (
            <div key={name} className="rounded-md border border-line p-3">
              <div className={`h-12 rounded ${bgClass}`} />
              <p className="mt-2 text-meta text-ink-muted">{name}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Category accents">
        <div className="flex flex-wrap gap-3">
          {CATEGORIES.map(([name, bgClass]) => (
            <div key={name} className="flex items-center gap-2 rounded-md border border-line px-3 py-2">
              <span className={`size-4 rounded-full ${bgClass}`} />
              <span className="text-meta text-ink-muted">{name}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Typography">
        <Card>
          <div className="space-y-3">
            {TYPE_SCALE.map((entry) => (
              <div key={entry.name} className="flex items-baseline gap-4">
                <span className="w-24 shrink-0 text-meta text-ink-subtle">{entry.name}</span>
                <span className={`tabular ${entry.className} text-ink`}>{entry.sample}</span>
              </div>
            ))}
          </div>
        </Card>
      </Section>

      <Section title="Metric cards">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Daily score" value={86} unit="/100" icon={Flame} accent="discipline" delta={4} deltaLabel="vs last week" />
          <MetricCard label="Study time" value="2h 15m" icon={GraduationCap} accent="learning" delta={-12} deltaLabel="vs last week" />
          <MetricCard label="Total volume" value="12,480" unit="lb" icon={Dumbbell} accent="fitness" delta={620} deltaLabel="vs last session" />
          <SkeletonCard />
        </div>
      </Section>

      <Section title="Stats, targets and rings">
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-3">
            <StatCard label="Sleep" value="7h 18m" icon={Moon} accent="recovery" hint="target 7h 30m" />
            <StatCard label="Streak" value="17 days" icon={Flame} accent="discipline" />
          </div>
          <div className="space-y-3">
            <ProgressCard label="Protein" value={142} target={165} unit="g" accent="fitness" />
            <ProgressCard label="Water" value={2.3} target={3} unit="L" icon={Droplets} accent="recovery" />
          </div>
          <Card>
            <div className="flex flex-wrap justify-around gap-4">
              <AttributeBadge name="Discipline" score={78} accent="discipline" />
              <AttributeBadge name="Knowledge" score={62} accent="learning" />
              <AttributeBadge name="Strength" score={71} accent="fitness" />
            </div>
          </Card>
        </div>
      </Section>

      <Section title="Charts">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Attributes" subtitle="This week vs last week">
            <AttributeRadar data={RADAR_SAMPLE} compareLabel="Last week" />
          </Card>
          <Card title="Discipline trend" subtitle="Last 7 days">
            <TrendChart data={TREND_SAMPLE} accent="discipline" name="Score" />
          </Card>
        </div>
      </Section>

      <Section title="Item icons">
        <Card subtitle="Checklist and attribute glyphs. Line icons from the same family as the chrome - they take an accent colour and stay sharp at any size.">
          <div className="flex flex-wrap items-center gap-3">
            {(['sun', 'workout', 'code', 'chess', 'sleep', 'water', 'breakfast', 'lunch'] as const).map((name) => (
              <ItemIcon key={name} name={name} />
            ))}
            <ItemIcon name="default" locked />
          </div>
        </Card>
      </Section>

      <Section title="Buttons and badges">
        <Card>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="secondary" loading>
              Saving
            </Button>
            <Badge tone="brand">Brand</Badge>
            <Badge tone="success">Success</Badge>
            <Badge tone="warning">Warning</Badge>
            <Badge tone="danger">Danger</Badge>
          </div>
        </Card>
      </Section>

      <Section title="Table, dialogs and empty state">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Leaderboard">
            <DataTable
              rows={TABLE_SAMPLE}
              rowKey={(row) => row.rank}
              isHighlighted={(row) => row.rank === 1}
              caption="Sample leaderboard"
              columns={[
                { key: 'rank', header: '#', render: (row) => row.rank },
                { key: 'name', header: 'Member', render: (row) => row.name },
                { key: 'xp', header: 'XP', align: 'right', render: (row) => row.xp.toLocaleString() },
              ]}
            />
          </Card>

          <Card title="Overlays">
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" onClick={() => setModalOpen(true)}>
                Open modal
              </Button>
              <Button variant="danger" onClick={() => setConfirmOpen(true)}>
                Delete something
              </Button>
            </div>
            <EmptyState
              title="No workouts yet"
              description="Complete your first workout to start tracking Strength."
              action={<Button variant="primary">Start workout</Button>}
            />
          </Card>
        </div>
      </Section>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Log a workout"
        description="Modals lock scroll, close on Escape, and trap focus on the panel."
        footer={
          <>
            <Button variant="ghost" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => setModalOpen(false)}>
              Save
            </Button>
          </>
        }
      >
        <p className="text-label text-ink-muted">Form content goes here.</p>
      </Modal>

      <ConfirmationDialog
        open={confirmOpen}
        title="Delete this entry?"
        description="This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={() => setConfirmOpen(false)}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  )
}
