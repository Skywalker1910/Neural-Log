import { useMemo, useState } from 'react'
import { m } from 'motion/react'
import {
  Award, BookOpen, Dumbbell, Flame, Info, Lock, Receipt, Sparkles, Sun,
  Trophy, UtensilsCrossed,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import type {
  AchievementCategory, AchievementTier, Badge as Achievement, XpEntry, XpLedger,
} from '../api/types'
import { useGamificationSummary, useXpLedger } from '../api/queries'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import { cn } from '../lib/cn'
import { spring } from '../lib/motion'
import { type Accent } from '../navigation'

const CATEGORY_META: Record<AchievementCategory, {
  label: string; icon: LucideIcon; accent: Accent
}> = {
  consistency: { label: 'Consistency', icon: Flame, accent: 'discipline' },
  training: { label: 'Training', icon: Dumbbell, accent: 'fitness' },
  nutrition: { label: 'Nutrition', icon: UtensilsCrossed, accent: 'lifestyle' },
  lifestyle: { label: 'Lifestyle', icon: Sun, accent: 'recovery' },
  learning: { label: 'Learning', icon: BookOpen, accent: 'learning' },
  mastery: { label: 'Mastery', icon: Sparkles, accent: 'goals' },
}

/**
 * Tier colours, deliberately not from the category palette.
 *
 * A gold achievement should read as gold whatever category it sits in - the
 * category is already carried by its section, and colouring tier by category
 * would make "gold" mean six different things.
 */
const TIER_STYLE: Record<AchievementTier, { ring: string; text: string; label: string }> = {
  bronze: { ring: 'border-[#b06a3b]/60', text: 'text-[#c98b5e]', label: 'Bronze' },
  silver: { ring: 'border-[#9aa4b2]/60', text: 'text-[#b9c2ce]', label: 'Silver' },
  gold: { ring: 'border-[#d4a63c]/70', text: 'text-[#e8c35c]', label: 'Gold' },
}

const SOURCE_LABEL: Record<string, string> = {
  checklist: 'Checklist',
  training: 'Training',
  nutrition: 'Nutrition',
  lifestyle: 'Lifestyle',
  learning: 'Learning',
  badge: 'Achievements',
}

function formatNumber(value: number) {
  return value >= 1000 ? value.toLocaleString() : String(value)
}

function AchievementCard({ achievement }: { achievement: Achievement }) {
  const tier = TIER_STYLE[achievement.tier]
  const pct = Math.round(achievement.progress * 100)

  return (
    <m.div
      layout
      transition={spring.snappy}
      className={cn(
        'flex min-w-0 flex-col gap-2 rounded-md border p-3 transition-colors',
        achievement.earned
          ? cn('bg-surface-raised', tier.ring)
          : 'border-line bg-surface-base',
      )}
    >
      <div className="flex items-start gap-2">
        <span
          className={cn(
            'flex size-8 shrink-0 items-center justify-center rounded-full border',
            achievement.earned
              ? cn(tier.ring, tier.text)
              : 'border-line text-ink-subtle',
          )}
          aria-hidden
        >
          {achievement.earned ? <Trophy size={15} /> : <Lock size={13} />}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className={cn('truncate text-label',
              achievement.earned ? 'text-ink' : 'text-ink-muted')}>
              {achievement.name}
            </span>
            <span className={cn('shrink-0 text-caption', tier.text)}>{tier.label}</span>
          </span>
          <span className="block text-meta text-ink-subtle">
            {achievement.description}
          </span>
        </span>

        {achievement.xp_reward > 0 && (
          <span className={cn('tabular shrink-0 text-meta',
            achievement.earned ? 'text-discipline' : 'text-ink-subtle')}>
            +{achievement.xp_reward}
          </span>
        )}
      </div>

      {/*
        The whole reason R7 rewrote the catalogue: a locked achievement says how
        close you are rather than sitting greyed out with no hint.
      */}
      {!achievement.earned && (
        <div className="flex flex-col gap-1">
          <div className="h-1.5 overflow-hidden rounded-full bg-surface-raised">
            <m.div
              className="h-full rounded-full bg-discipline"
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={spring.soft}
            />
          </div>
          <span className="tabular text-caption text-ink-subtle">
            {formatNumber(achievement.current)} of {formatNumber(achievement.threshold)}
          </span>
        </div>
      )}
    </m.div>
  )
}

function XpBreakdown({ ledger }: { ledger: XpLedger }) {
  const measured = ledger.evidence.measured ?? 0
  const claimed = ledger.evidence.claimed ?? 0
  const total = measured + claimed
  const measuredPct = total > 0 ? Math.round((measured / total) * 100) : 0

  const max = Math.max(...ledger.by_source.map((row) => row.xp), 1)

  return (
    <div className="flex flex-col gap-4">
      <div>
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <span className="text-meta text-ink-muted">Evidenced vs claimed</span>
          <span className="tabular text-meta text-ink">{measuredPct}% evidenced</span>
        </div>
        <div className="flex h-2 overflow-hidden rounded-full bg-surface-raised">
          <m.div
            className="h-full bg-success"
            initial={{ width: 0 }}
            animate={{ width: `${measuredPct}%` }}
            transition={spring.soft}
          />
          <div className="h-full flex-1 bg-discipline/50" />
        </div>
        <p className="mt-1 flex items-start gap-1.5 text-caption text-ink-subtle">
          <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
          Green is XP from work you logged — sets, sessions, meals, nights. The
          rest is from ticking the daily checklist, which pays less on any day you
          also logged the real thing.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        {ledger.by_source.map((row, index) => (
          <div key={row.source} className="flex items-center gap-3">
            <span className="w-24 shrink-0 truncate text-meta text-ink-muted">
              {SOURCE_LABEL[row.source] ?? row.source}
            </span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-raised">
              <m.div
                className="h-full rounded-full bg-discipline"
                initial={{ width: 0 }}
                animate={{ width: `${(row.xp / max) * 100}%` }}
                transition={{ ...spring.soft, delay: index * 0.04 }}
              />
            </div>
            <span className="tabular w-14 shrink-0 text-right text-meta text-ink-subtle">
              {formatNumber(row.xp)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function LedgerRow({ entry }: { entry: XpEntry }) {
  return (
    <div className="flex min-w-0 items-center gap-3 border-b border-line py-2 last:border-0">
      <span className="tabular w-20 shrink-0 text-meta text-ink-subtle">{entry.date}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-meta text-ink">{entry.reason}</span>
        {entry.capped_from != null && (
          <span className="block text-caption text-warning">
            capped — would have been {entry.capped_from}
          </span>
        )}
      </span>
      {entry.evidence === 'claimed' && (
        <Badge tone="neutral" className="shrink-0 whitespace-nowrap">claimed</Badge>
      )}
      <span className="tabular w-12 shrink-0 text-right text-label text-ink">
        +{entry.xp}
      </span>
    </div>
  )
}

export function Achievements() {
  const summary = useGamificationSummary()
  const ledger = useXpLedger(40)
  const [filter, setFilter] = useState<AchievementCategory | 'all'>('all')

  const grouped = useMemo(() => {
    const badges = summary.data?.badges ?? []
    const order = Object.keys(CATEGORY_META) as AchievementCategory[]
    return order
      .map((category) => ({
        category,
        items: badges.filter((badge) => badge.category === category),
      }))
      .filter((group) => group.items.length > 0)
  }, [summary.data])

  const counts = useMemo(() => {
    const badges = summary.data?.badges ?? []
    return {
      earned: badges.filter((badge) => badge.earned).length,
      total: badges.length,
      // The one you are closest to but have not got. More motivating than a
      // count, and it is only answerable because progress is real data now.
      nearest: badges
        .filter((badge) => !badge.earned && badge.progress > 0)
        .sort((a, b) => b.progress - a.progress)[0],
    }
  }, [summary.data])

  const visible = filter === 'all'
    ? grouped
    : grouped.filter((group) => group.category === filter)

  return (
    <>
      <PageHeader
        title="Achievements"
        description="What you have unlocked, and how close you are to the rest."
        icon={Trophy}
        accent="discipline"
      />

      <QueryBoundary query={summary} loading={<SkeletonGrid />}>
        {(data) => (
          <RevealGroup className="flex flex-col gap-4">
            <Reveal className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard label="Unlocked" value={`${counts.earned} / ${counts.total}`}
                        icon={Trophy} accent="discipline" />
              <StatCard label="Level" value={data.level} icon={Award} accent="goals"
                        hint={`${data.xp_into_level} / ${data.xp_for_next_level} XP`} />
              <StatCard label="Total XP" value={formatNumber(data.total_xp)}
                        icon={Sparkles} accent="brand" />
              <StatCard label="Streak" value={`${data.current_streak} ${data.current_streak === 1 ? 'day' : 'days'}`}
                        icon={Flame} accent="fitness"
                        hint={data.streak_multiplier_pct
                          ? `+${data.streak_multiplier_pct}% XP` : undefined} />
            </Reveal>

            {counts.nearest && (
              <Reveal>
                <Card title="Closest to unlocking" icon={Sparkles} accent="discipline">
                  <AchievementCard achievement={counts.nearest} />
                </Card>
              </Reveal>
            )}

            <Reveal>
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => setFilter('all')}
                  aria-pressed={filter === 'all'}
                  className={cn(
                    'rounded-full border px-3 py-1 text-meta transition-colors',
                    filter === 'all'
                      ? 'border-discipline bg-discipline/15 text-discipline'
                      : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
                  )}
                >
                  All
                </button>
                {grouped.map(({ category }) => (
                  <button
                    key={category}
                    type="button"
                    onClick={() => setFilter(category)}
                    aria-pressed={filter === category}
                    className={cn(
                      'rounded-full border px-3 py-1 text-meta transition-colors',
                      filter === category
                        ? 'border-discipline bg-discipline/15 text-discipline'
                        : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
                    )}
                  >
                    {CATEGORY_META[category].label}
                  </button>
                ))}
              </div>
            </Reveal>

            {visible.map(({ category, items }) => {
              const meta = CATEGORY_META[category]
              const earned = items.filter((item) => item.earned).length
              return (
                <Reveal key={category}>
                  <Card
                    title={meta.label}
                    subtitle={`${earned} of ${items.length} unlocked`}
                    icon={meta.icon}
                    accent={meta.accent}
                  >
                    <div className="grid gap-2 lg:grid-cols-2">
                      {items.map((achievement) => (
                        <AchievementCard key={achievement.code} achievement={achievement} />
                      ))}
                    </div>
                  </Card>
                </Reveal>
              )
            })}

            <Reveal>
              <Card
                title="Where your XP came from"
                subtitle="Last 30 days"
                icon={Receipt}
                accent="discipline"
              >
                <QueryBoundary query={ledger} loading={<SkeletonGrid />}>
                  {(data2) => (
                    data2.by_source.length === 0
                      ? <p className="text-label text-ink-subtle">Nothing earned yet.</p>
                      : <XpBreakdown ledger={data2} />
                  )}
                </QueryBoundary>
              </Card>
            </Reveal>

            <Reveal>
              <Card
                title="Recent XP"
                subtitle="Every award, and why"
                icon={Receipt}
                accent="brand"
              >
                <QueryBoundary query={ledger} loading={<SkeletonGrid />}>
                  {(data2) => (
                    data2.entries.length === 0 ? (
                      <p className="text-label text-ink-subtle">
                        Nothing yet. Log a workout, a study session or your daily
                        checklist and it shows up here with the reason.
                      </p>
                    ) : (
                      <div className="flex flex-col">
                        {data2.entries.map((entry) => (
                          <LedgerRow key={entry.id} entry={entry} />
                        ))}
                      </div>
                    )
                  )}
                </QueryBoundary>
              </Card>
            </Reveal>

            <Reveal>
              <p className="flex items-start gap-1.5 text-caption text-ink-subtle">
                <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
                Each source has a daily cap, and trivially small entries earn
                nothing — a three-minute study session or a workout with no working
                sets. Capped awards say so above, rather than silently paying less.
              </p>
            </Reveal>
          </RevealGroup>
        )}
      </QueryBoundary>
    </>
  )
}
