import { CalendarCheck, ChartLine, Flame, House, Radar, Sparkles, TrendingUp } from 'lucide-react'

import { m } from 'motion/react'

import type { AttributeScore, HomeSummary } from '../api/types'
import { useHomeSummary } from '../api/queries'
import { AttributeRadar, TrendChart, type AttributeDatum } from '../components/charts'
import { PageHeader } from '../components/layout/PageHeader'
import { AnimatedNumber } from '../components/ui/AnimatedNumber'
import { AttributeBadge } from '../components/ui/AttributeBadge'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { MetricCard } from '../components/ui/MetricCard'
import { ProgressRing } from '../components/ui/ProgressRing'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { EASE } from '../lib/motion'
import type { Accent } from '../navigation'

/**
 * Eight attributes over seven accent tokens. Strength and Stamina deliberately
 * share the fitness accent - they are both physical, and inventing an eighth
 * colour for the sake of uniqueness would weaken the category language the rest
 * of the app uses.
 */
const ATTRIBUTE_ACCENT: Record<string, Accent> = {
  Discipline: 'discipline',
  Knowledge: 'learning',
  Strength: 'fitness',
  Stamina: 'fitness',
  Agility: 'lifestyle',
  Recovery: 'recovery',
  Consistency: 'goals',
  Focus: 'brand',
}

/** The minimum active attributes before a radar shape means anything. */
const RADAR_MIN_AXES = 3

function attributeHint(attribute: AttributeScore): string | undefined {
  switch (attribute.status) {
    case 'locked':
      return attribute.unlocks_in ? `Unlocks in ${attribute.unlocks_in}` : 'Locked'
    case 'unobserved':
      return 'Not in your Path'
    case 'calibrating':
      return attribute.needs_days ? `${attribute.needs_days} more days` : 'Calibrating'
    default:
      return undefined
  }
}

function greeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

function AttributePanel({ attributes }: { attributes: AttributeScore[] }) {
  const active = attributes.filter((a) => a.status === 'active' && a.score !== null)
  const unmeasured = attributes.filter((a) => a.status !== 'active')

  // All eight axes are always plotted, even the unscored ones, so the shape is
  // comparable between visits - a radar whose axes come and go cannot be read.
  // The caption below says which of them are not measured yet, so a zero on the
  // chart is never mistaken for "you scored nothing".
  const data: AttributeDatum[] = attributes.map((attribute) => ({
    attribute: attribute.attribute,
    value: attribute.status === 'active' ? (attribute.score ?? 0) : 0,
  }))

  return (
    <Card
      title="Character sheet"
      subtitle="Built from what you actually logged"
      icon={Radar}
      accent="goals"
    >
      {active.length < RADAR_MIN_AXES ? (
        <EmptyState
          icon={Radar}
          title="Your character sheet is still forming"
          description={
            <>
              Attributes need a few days of history before a score means anything.
              {active.length > 0 && ` ${active.length} of 8 so far.`}
            </>
          }
        />
      ) : (
        <>
          <AttributeRadar data={data} height={300} />
          {unmeasured.length > 0 && (
            <p className="mt-2 text-meta text-ink-subtle">
              {unmeasured.length} of 8 not measured yet —{' '}
              {unmeasured.map((a) => a.attribute).join(', ')}. They sit at the centre
              rather than being hidden, so the shape stays comparable.
            </p>
          )}
        </>
      )}

      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {attributes.map((attribute) => (
          <AttributeBadge
            key={attribute.attribute}
            name={attribute.attribute}
            score={attribute.score}
            status={attribute.status}
            hint={attributeHint(attribute)}
            confidence={attribute.confidence}
            accent={ATTRIBUTE_ACCENT[attribute.attribute] ?? 'brand'}
            size={72}
          />
        ))}
      </div>
    </Card>
  )
}

function TodayPanel({ today }: { today: HomeSummary['today'] }) {
  return (
    <Card title="Today" subtitle={today.logged ? 'Logged' : 'Not logged yet'} icon={CalendarCheck}>
      {today.logged ? (
        <div className="flex items-center gap-5">
          <ProgressRing
            value={today.completion_pct}
            size={96}
            accent="lifestyle"
            ariaLabel={`Today ${today.completion_pct}% complete`}
            label={
              <AnimatedNumber
                value={today.completion_pct}
                suffix="%"
                className="tabular text-section font-bold text-lifestyle"
              />
            }
          />
          <div>
            <p className="tabular text-metric text-ink">
              <AnimatedNumber value={today.items_completed} />
              <span className="text-section text-ink-subtle"> / {today.items_total}</span>
            </p>
            <p className="text-label text-ink-muted">items completed</p>
          </div>
        </div>
      ) : (
        <EmptyState
          icon={CalendarCheck}
          title="Nothing logged today"
          description="Run through your Path and today's numbers appear here."
        />
      )}
    </Card>
  )
}

function TrendPanel({ trend }: { trend: HomeSummary['trend'] }) {
  const points = trend
    .filter((point) => point.daily_score !== null)
    .map((point) => ({
      // Long ranges would overlap; show day-of-month only.
      label: point.date.slice(8),
      value: point.daily_score as number,
    }))

  return (
    <Card title="Daily score" subtitle="Last 14 days" icon={ChartLine} accent="learning">
      {points.length < 2 ? (
        <EmptyState
          icon={TrendingUp}
          title="Not enough history for a trend"
          description="Two logged days and this starts drawing."
        />
      ) : (
        <TrendChart data={points} accent="learning" height={220} name="Daily score" />
      )}
    </Card>
  )
}

export function Home() {
  const query = useHomeSummary()

  return (
    <>
      <PageHeader
        title={greeting()}
        description={new Date().toLocaleDateString(undefined, {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
        })}
        icon={House}
      />

      <QueryBoundary query={query} loading={<SkeletonGrid />}>
        {(data) => (
          <RevealGroup className="flex flex-col gap-4" step={0.07}>
            <Reveal>
            <Card accent="discipline" bodyClassName="flex flex-wrap items-center gap-6">
              <div className="flex items-center gap-4">
                <span className="flex size-14 items-center justify-center rounded-full bg-discipline/12 text-discipline">
                  <Sparkles size={24} aria-hidden />
                </span>
                <div>
                  <p className="tabular text-metric text-ink">
                    Level <AnimatedNumber value={data.level} />
                  </p>
                  <p className="text-label text-ink-muted">
                    <AnimatedNumber className="tabular" value={data.xp_into_level} /> /{' '}
                    <span className="tabular">{data.xp_for_next_level}</span> XP to next level
                  </p>
                </div>
              </div>
              <div className="h-2 min-w-40 flex-1 overflow-hidden rounded-full bg-surface-raised">
                <m.div
                  className="h-full rounded-full bg-discipline"
                  initial={{ width: 0 }}
                  animate={{
                    width: `${Math.min(
                      100,
                      data.xp_for_next_level
                        ? (data.xp_into_level / data.xp_for_next_level) * 100
                        : 0,
                    )}%`,
                  }}
                  transition={{ duration: 0.9, ease: EASE }}
                />
              </div>
            </Card>
            </Reveal>

            <RevealGroup className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" step={0.06}>
              <Reveal><MetricCard
                label="Daily score"
                value={data.daily_score === null ? '–' : <AnimatedNumber value={data.daily_score} />}
                icon={Sparkles}
                accent="brand"
                footer={data.daily_score === null ? 'Log a day to start' : undefined}
              /></Reveal>
              <Reveal><MetricCard
                label="Discipline"
                value={data.discipline_score === null ? '–' : <AnimatedNumber value={data.discipline_score} />}
                icon={ChartLine}
                accent="discipline"
                footer={data.discipline_score === null ? 'Needs a few days' : undefined}
              /></Reveal>
              <Reveal><MetricCard
                label="Streak"
                value={<AnimatedNumber value={data.current_streak} />}
                unit={data.current_streak === 1 ? 'day' : 'days'}
                icon={Flame}
                accent="fitness"
                footer={
                  data.streak_multiplier_pct > 0
                    ? `+${data.streak_multiplier_pct}% XP`
                    : undefined
                }
              /></Reveal>
              <Reveal><MetricCard
                label="Days logged"
                value={<AnimatedNumber value={data.days_logged} />}
                icon={CalendarCheck}
                accent="lifestyle"
              /></Reveal>
            </RevealGroup>

            <RevealGroup className="grid gap-4 lg:grid-cols-2" step={0.06}>
              <Reveal><TodayPanel today={data.today} /></Reveal>
              <Reveal><TrendPanel trend={data.trend} /></Reveal>
            </RevealGroup>

            <Reveal><AttributePanel attributes={data.attributes} /></Reveal>
          </RevealGroup>
        )}
      </QueryBoundary>
    </>
  )
}
