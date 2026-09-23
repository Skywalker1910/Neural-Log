import { Link } from 'react-router'
import { ArrowRight, Scale, Target, User } from 'lucide-react'

import { useAttributes, useCurrentUser, useOnboarding, useOnboardingPrompt } from '../api/queries'
import type { AttributeScore, OnboardingState } from '../api/types'
import { PageHeader } from '../components/layout/PageHeader'
import { ProfileIdentity } from '../components/ui/ProfileIdentity'
import { AttributeBadge } from '../components/ui/AttributeBadge'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { ATTRIBUTE_ACCENT, attributeHint } from '../lib/attributes'
import { shortDate } from '../lib/date'

const SEX_LABELS: Record<string, string> = {
  male: 'Male',
  female: 'Female',
  unspecified: 'Prefer not to say',
}

const ACTIVITY_LABELS: Record<string, string> = {
  sedentary: 'Sedentary',
  light: 'Light',
  moderate: 'Moderate',
  active: 'Active',
  'very-active': 'Very active',
}

const GOAL_LABELS: Record<string, string> = {
  cut: 'Lose fat',
  maintain: 'Maintain',
  bulk: 'Build muscle',
}

function Detail({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-meta text-ink-subtle">{label}</dt>
      <dd className="tabular mt-0.5 break-words text-section font-semibold text-ink">{value}</dd>
      {note && <p className="mt-0.5 text-meta text-ink-subtle">{note}</p>}
    </div>
  )
}

/**
 * Baselines, shown with the honesty the rest of the app uses.
 *
 * Every value is either present or a dash with a reason. None of them is a
 * score - they are arithmetic on what you entered, and the page says so, because
 * a big number in a card is read as an achievement unless it is labelled.
 */
function BaselinePanel({ state }: { state: OnboardingState }) {
  const { baselines, targets } = state

  return (
    <Card
      title="Baselines"
      subtitle="Computed from your details. Not scores."
      icon={Scale}
      accent="recovery"
      action={
        <Link to="/welcome">
          <Button size="sm" variant="secondary" icon={ArrowRight} iconPosition="end">
            Update
          </Button>
        </Link>
      }
    >
      {baselines.missing.length > 0 && (
        <p className="mb-4 rounded-md border border-line bg-surface-base px-4 py-3 text-label text-ink-muted">
          Add your {baselines.missing.join(', ')} and these fill in. Nothing is estimated from
          what is missing.
        </p>
      )}

      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Detail
          label="BMI"
          value={baselines.bmi ? String(baselines.bmi) : '—'}
          note="Mass over height squared. It cannot see muscle, so there is no category."
        />
        <Detail
          label="BMR"
          value={baselines.bmr ? `${baselines.bmr.toLocaleString()} kcal` : '—'}
          note="At rest. Mifflin-St Jeor."
        />
        <Detail
          label="Daily energy"
          value={baselines.tdee ? `${baselines.tdee.toLocaleString()} kcal` : '—'}
          note="BMR scaled by activity."
        />
        <Detail
          label="Calorie target"
          value={targets.calories ? `${targets.calories.toLocaleString()} kcal` : '—'}
          note={targets.sources.calories === 'set' ? 'Set by you' : 'Estimated'}
        />
        <Detail
          label="Protein target"
          value={targets.protein_g ? `${targets.protein_g} g` : '—'}
          note={targets.sources.protein === 'set' ? 'Set by you' : 'Estimated'}
        />
        <Detail
          label="Weekly study"
          value={`${targets.weekly_study_minutes} min`}
          note="What Knowledge is measured against."
        />
      </dl>
    </Card>
  )
}

function AttributePanel({ attributes }: { attributes: AttributeScore[] }) {
  const measured = attributes.filter((attribute) => attribute.score !== null)

  return (
    <Card
      title="Attributes"
      subtitle={
        measured.length === attributes.length
          ? 'All eight measured'
          : `${measured.length} of ${attributes.length} measured — the rest need more history`
      }
      icon={Target}
      accent="goals"
    >
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {attributes.map((attribute) => (
          <AttributeBadge
            key={attribute.attribute}
            name={attribute.attribute}
            score={attribute.score}
            status={attribute.status}
            hint={attributeHint(attribute)}
            confidence={attribute.confidence}
            accent={ATTRIBUTE_ACCENT[attribute.attribute] ?? 'brand'}
          />
        ))}
      </div>
      <p className="mt-4 text-meta text-ink-subtle">
        These come from what you logged, never from what you told us during setup. An
        attribute stays unmeasured until there is enough history for a number to mean
        something.
      </p>
    </Card>
  )
}

export function Profile() {
  const user = useCurrentUser()
  const onboarding = useOnboarding()
  const attributes = useAttributes()
  const { reopen } = useOnboardingPrompt()

  return (
    <>
      <PageHeader
        title="Profile"
        description="Your details, the baselines they produce, and the attributes you have earned."
        icon={User}
        accent="brand"
        actions={
          user.data?.is_admin ? <Badge tone="neutral">Admin</Badge> : undefined
        }
      />

      <Reveal className="mb-5"><ProfileIdentity /></Reveal>

      <QueryBoundary query={onboarding} loading={<SkeletonGrid />}>
        {(state) => (
          <RevealGroup className="flex flex-col gap-4" step={0.05}>
            {!state.completed && (
              <Reveal>
                <Card bodyClassName="flex flex-wrap items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-label font-semibold text-ink">
                      Setup is unfinished — {state.steps.length - state.step} steps left
                    </p>
                    <p className="text-meta text-ink-muted">
                      {state.dismissed
                        ? 'You declined the prompt, which is why it stopped appearing on Home.'
                        : 'Your targets are estimated until you finish.'}
                    </p>
                  </div>
                  <Link to="/welcome" onClick={() => state.dismissed && reopen.mutate()}>
                    <Button variant="primary" icon={ArrowRight} iconPosition="end">
                      {state.step > 0 ? 'Resume setup' : 'Start setup'}
                    </Button>
                  </Link>
                </Card>
              </Reveal>
            )}

            <Reveal>
              <Card
                title="Details"
                subtitle={
                  state.completed_at
                    ? `Set up ${shortDate(state.completed_at.slice(0, 10))}`
                    : 'Whatever you have told us so far'
                }
                icon={User}
                accent="brand"
                action={
                  <Link to="/welcome">
                    <Button size="sm" variant="secondary" icon={ArrowRight} iconPosition="end">
                      Edit
                    </Button>
                  </Link>
                }
              >
                <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <Detail label="Username" value={user.data?.username ?? '—'} />
                  <Detail
                    label="Age"
                    value={state.baselines.age ? `${state.baselines.age}` : '—'}
                    note={state.answers.birth_year ? `Born ${state.answers.birth_year}` : undefined}
                  />
                  <Detail
                    label="Height"
                    value={state.answers.height_cm ? `${state.answers.height_cm} cm` : '—'}
                  />
                  <Detail
                    label="Weight"
                    value={state.answers.weight_kg ? `${state.answers.weight_kg} kg` : '—'}
                    note="Latest measurement"
                  />
                  <Detail
                    label="Sex"
                    value={state.answers.sex ? SEX_LABELS[state.answers.sex] ?? '—' : '—'}
                  />
                  <Detail
                    label="Activity"
                    value={
                      state.answers.activity_level
                        ? ACTIVITY_LABELS[state.answers.activity_level] ?? '—'
                        : '—'
                    }
                  />
                  <Detail
                    label="Goal"
                    value={state.answers.goal ? GOAL_LABELS[state.answers.goal] ?? '—' : '—'}
                  />
                  <Detail
                    label="Check-in"
                    value={`${state.survey.filter((q) => q.type !== 'rating').length} questions`}
                    note="Shared by everyone"
                  />
                </dl>
              </Card>
            </Reveal>

            <Reveal>
              <BaselinePanel state={state} />
            </Reveal>

            <Reveal>
              <QueryBoundary query={attributes} loading={<SkeletonGrid />}>
                {(data) => <AttributePanel attributes={data.attributes} />}
              </QueryBoundary>
            </Reveal>
          </RevealGroup>
        )}
      </QueryBoundary>
    </>
  )
}
