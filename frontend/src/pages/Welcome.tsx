import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { AnimatePresence, m } from 'motion/react'
import { ArrowLeft, ArrowRight, Check, Sparkles } from 'lucide-react'

import { ApiError } from '../api/client'
import { useOnboarding, useSaveOnboarding } from '../api/queries'
import type { OnboardingAnswers, OnboardingState } from '../api/types'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ChoiceGroup, Field, Select, TextInput } from '../components/ui/Field'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { cn } from '../lib/cn'
import { duration, EASE } from '../lib/motion'
import { usePrefersReducedMotion } from '../lib/usePrefersReducedMotion'

type Answers = Partial<OnboardingAnswers>

const ACTIVITY = [
  { value: 'sedentary', label: 'Sedentary', hint: 'Desk job, little deliberate movement' },
  { value: 'light', label: 'Light', hint: 'Light exercise 1-3 days a week' },
  { value: 'moderate', label: 'Moderate', hint: '3-5 days a week' },
  { value: 'active', label: 'Active', hint: '6-7 days a week' },
  { value: 'very-active', label: 'Very active', hint: 'Hard daily training or a physical job' },
]

const GOALS = [
  { value: 'cut', label: 'Lose fat', hint: '20% below maintenance' },
  { value: 'maintain', label: 'Maintain', hint: 'Hold steady' },
  { value: 'bulk', label: 'Build muscle', hint: '10% above maintenance' },
]

const PATHS = [
  { value: 'Batman Path', label: 'Batman', hint: 'Discipline and relentless preparation' },
  { value: 'Thor Path', label: 'Thor', hint: 'Strength and physical dominance' },
  { value: 'Captain America Path', label: 'Captain America', hint: 'Consistency and duty' },
  { value: 'Ironman Path', label: 'Ironman', hint: 'Learning and invention' },
]

/** Minutes <-> "7h 30m", so sleep is entered in the units people think in. */
function hoursLabel(minutes: number | null | undefined): string {
  if (!minutes) return ''
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours}h ${rest}m` : `${hours}h`
}

function StepDots({ total, current }: { total: number; current: number }) {
  return (
    <div className="flex items-center gap-1.5" aria-hidden>
      {Array.from({ length: total }, (_, index) => (
        <span
          key={index}
          className={cn(
            'h-1.5 rounded-pill transition-all duration-300 ease-apple',
            index === current ? 'w-6 bg-brand' : 'w-1.5 bg-surface-overlay',
          )}
        />
      ))}
    </div>
  )
}

function Baselines({ state }: { state: OnboardingState }) {
  const { baselines, targets } = state

  const rows: { label: string; value: string; note?: string }[] = [
    { label: 'BMI', value: baselines.bmi ? String(baselines.bmi) : '—',
      note: 'A mass-to-height ratio. It cannot see muscle, so there is no category attached.' },
    { label: 'BMR', value: baselines.bmr ? `${baselines.bmr.toLocaleString()} kcal` : '—',
      note: 'What your body uses at rest. Mifflin-St Jeor.' },
    { label: 'Daily energy', value: baselines.tdee ? `${baselines.tdee.toLocaleString()} kcal` : '—',
      note: 'BMR scaled by how active you said you are.' },
    { label: 'Calorie target', value: targets.calories ? `${targets.calories.toLocaleString()} kcal` : '—',
      note: targets.sources.calories === 'set' ? 'You set this by hand.' : 'Estimated from your goal.' },
    { label: 'Protein target', value: targets.protein_g ? `${targets.protein_g} g` : '—' },
    { label: 'Weekly study', value: `${targets.weekly_study_minutes} min` },
  ]

  return (
    <div className="flex flex-col gap-4">
      {baselines.missing.length > 0 && (
        <p className="rounded-md border border-line bg-surface-base px-4 py-3 text-label text-ink-muted">
          Add your {baselines.missing.join(', ')} and these fill in. Nothing is guessed from
          what is missing.
        </p>
      )}

      <dl className="grid gap-3 sm:grid-cols-2">
        {rows.map((row) => (
          <div key={row.label} className="min-w-0 rounded-md border border-line bg-surface-base p-4">
            <dt className="text-meta text-ink-subtle">{row.label}</dt>
            <dd className="tabular mt-0.5 text-section font-semibold text-ink">{row.value}</dd>
            {row.note && <p className="mt-1 text-meta text-ink-subtle">{row.note}</p>}
          </div>
        ))}
      </dl>

      <p className="text-meta text-ink-subtle">
        None of this is a score. Your attributes stay unmeasured until you have logged a few
        real days — what you just told us sets the targets they will be measured against.
      </p>
    </div>
  )
}

function StepFields({
  stepKey,
  answers,
  errors,
  set,
  state,
}: {
  stepKey: string
  answers: Answers
  errors: Record<string, string>
  set: (patch: Answers) => void
  state: OnboardingState
}) {
  switch (stepKey) {
    case 'profile':
      return (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Birth year" hint="Only the year — a full date is more than a calorie estimate justifies." error={errors.birth_year}>
            {(id) => (
              <TextInput
                id={id} type="number" inputMode="numeric" placeholder="1995"
                value={answers.birth_year ?? ''}
                onChange={(e) => set({ birth_year: e.target.value ? Number(e.target.value) : null })}
              />
            )}
          </Field>
          <Field label="Height" hint="Centimetres." error={errors.height_cm}>
            {(id) => (
              <TextInput
                id={id} type="number" inputMode="decimal" placeholder="178"
                value={answers.height_cm ?? ''}
                onChange={(e) => set({ height_cm: e.target.value ? Number(e.target.value) : null })}
              />
            )}
          </Field>
          <Field label="Sex" hint="Shifts the BMR formula by about 160 kcal. Decline and the error is split." error={errors.sex} className="sm:col-span-2">
            {(id) => (
              <Select id={id} value={answers.sex ?? ''} onChange={(e) => set({ sex: e.target.value || null })}>
                <option value="">Prefer not to say</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
              </Select>
            )}
          </Field>
        </div>
      )

    case 'activity':
      return (
        <div className="flex flex-col gap-5">
          <ChoiceGroup
            name="Activity level"
            value={answers.activity_level ?? null}
            options={ACTIVITY}
            onChange={(activity_level) => set({ activity_level })}
          />
          <Field
            label="Training days a week"
            hint="What a full week of volume means for you. Leave blank and it assumes four."
            error={errors.training_days_per_week}
          >
            {(id) => (
              <TextInput
                id={id} type="number" inputMode="numeric" min={0} max={7} placeholder="4"
                className="sm:max-w-48"
                value={answers.training_days_per_week ?? ''}
                onChange={(e) =>
                  set({ training_days_per_week: e.target.value ? Number(e.target.value) : null })
                }
              />
            )}
          </Field>
        </div>
      )

    case 'body_goal':
      return (
        <div className="flex flex-col gap-5">
          <ChoiceGroup
            name="Goal"
            value={answers.goal ?? null}
            options={GOALS}
            onChange={(goal) => set({ goal })}
          />
          <Field label="Current weight" hint="Kilograms. Stored as a measurement, so it can move." error={errors.weight_kg}>
            {(id) => (
              <TextInput
                id={id} type="number" inputMode="decimal" step="0.1" placeholder="75"
                className="sm:max-w-48"
                value={answers.weight_kg ?? ''}
                onChange={(e) => set({ weight_kg: e.target.value ? Number(e.target.value) : null })}
              />
            )}
          </Field>
        </div>
      )

    case 'sleep':
      return (
        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label="Target sleep"
            hint={`Minutes. ${hoursLabel(answers.sleep_target_minutes) || '8h'} — this one is scored.`}
            error={errors.sleep_target_minutes}
          >
            {(id) => (
              <TextInput
                id={id} type="number" inputMode="numeric" step="15" placeholder="480"
                value={answers.sleep_target_minutes ?? ''}
                onChange={(e) => set({ sleep_target_minutes: e.target.value ? Number(e.target.value) : null })}
              />
            )}
          </Field>
          <Field label="Usual bedtime" hint="For display and prefill." error={errors.target_bedtime}>
            {(id) => (
              <TextInput
                id={id} type="time"
                value={answers.target_bedtime ?? ''}
                onChange={(e) => set({ target_bedtime: e.target.value || null })}
              />
            )}
          </Field>
          <Field label="Usual wake time" hint="For display and prefill." error={errors.target_wake_time}>
            {(id) => (
              <TextInput
                id={id} type="time"
                value={answers.target_wake_time ?? ''}
                onChange={(e) => set({ target_wake_time: e.target.value || null })}
              />
            )}
          </Field>
        </div>
      )

    case 'learning':
      return (
        <Field
          label="Weekly study target"
          hint={`Minutes a week. ${hoursLabel(answers.weekly_study_minutes) || '5h'} — Knowledge is measured against this.`}
          error={errors.weekly_study_minutes}
        >
          {(id) => (
            <TextInput
              id={id} type="number" inputMode="numeric" step="30" placeholder="300"
              className="sm:max-w-48"
              value={answers.weekly_study_minutes ?? ''}
              onChange={(e) => set({ weekly_study_minutes: e.target.value ? Number(e.target.value) : null })}
            />
          )}
        </Field>
      )

    case 'path':
      return (
        <ChoiceGroup
          name="Path"
          value={answers.selected_path ?? null}
          options={PATHS}
          onChange={(selected_path) => set({ selected_path })}
        />
      )

    case 'baselines':
      return <Baselines state={state} />

    default:
      return null
  }
}

function Flow({ state }: { state: OnboardingState }) {
  const save = useSaveOnboarding()
  const navigate = useNavigate()
  const reduced = usePrefersReducedMotion()

  const [index, setIndex] = useState(() => Math.min(state.step, state.steps.length - 1))
  const [draft, setDraft] = useState<Answers>({})
  const [errors, setErrors] = useState<Record<string, string>>({})

  // Server answers underneath, unsaved edits on top - derived rather than copied
  // into state by an effect, so a refetch never clobbers something half-typed.
  const answers = useMemo(() => ({ ...state.answers, ...draft }), [state.answers, draft])

  const step = state.steps[index]
  const last = index === state.steps.length - 1

  /* Errors belong to the step that produced them, so moving clears them. Done
     here rather than in an effect on `index`: the effect ran on the first render
     too, and "clear on navigate" is a property of navigating, not of the index
     having a value. */
  const goTo = (next: number) => {
    setIndex(next)
    setErrors({})
  }

  const commit = async (next: number, complete = false) => {
    try {
      await save.mutateAsync({ answers: draft, step: next, complete })
      setDraft({})
      if (complete) navigate('/', { replace: true })
      else goTo(next)
    } catch (error) {
      // The server validates closed sets and ranges; surface it per field rather
      // than as one banner, so it is obvious which answer to fix.
      setErrors(error instanceof ApiError ? error.fields : {})
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col justify-center gap-6 px-4 py-10">
      <div className="flex items-center justify-between gap-4">
        <span className="flex items-center gap-2 text-label text-ink-muted">
          <span className="flex size-7 items-center justify-center rounded-md bg-brand text-white">
            <Sparkles size={15} aria-hidden />
          </span>
          Setting up
        </span>
        <StepDots total={state.steps.length} current={index} />
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <m.div
          key={step.key}
          initial={reduced ? { opacity: 0 } : { opacity: 0, x: 16 }}
          animate={reduced ? { opacity: 1 } : { opacity: 1, x: 0 }}
          exit={reduced ? { opacity: 0 } : { opacity: 0, x: -16 }}
          transition={{ duration: duration.base, ease: EASE }}
        >
          <Card>
            <div className="flex flex-col gap-5">
              <div>
                <p className="text-meta uppercase tracking-wide text-ink-subtle">
                  Step {index + 1} of {state.steps.length}
                </p>
                <h1 className="mt-1 text-heading text-ink">{step.title}</h1>
                <p className="mt-1 text-label text-ink-muted">{step.blurb}</p>
              </div>

              <StepFields
                stepKey={step.key}
                answers={answers}
                errors={errors}
                set={(patch) => setDraft((current) => ({ ...current, ...patch }))}
                state={state}
              />
            </div>
          </Card>
        </m.div>
      </AnimatePresence>

      <div className="flex items-center justify-between gap-3">
        <Button
          variant="ghost"
          icon={ArrowLeft}
          disabled={index === 0 || save.isPending}
          onClick={() => goTo(Math.max(0, index - 1))}
        >
          Back
        </Button>

        <div className="flex items-center gap-2">
          {!last && (
            // Skip discards this step's edits rather than saving a half-answer.
            <Button
              variant="ghost"
              disabled={save.isPending}
              onClick={() => {
                setDraft({})
                goTo(index + 1)
              }}
            >
              Skip
            </Button>
          )}
          <Button
            variant="primary"
            icon={last ? Check : ArrowRight}
            iconPosition="end"
            loading={save.isPending}
            onClick={() => commit(last ? index : index + 1, last)}
          >
            {last ? 'Finish' : 'Continue'}
          </Button>
        </div>
      </div>

      {save.isError && Object.keys(errors).length === 0 && (
        <p className="text-label text-danger">
          Could not save that step. Your answers are still here — try again.
        </p>
      )}
    </div>
  )
}

/**
 * The first-run flow.
 *
 * Reachable rather than enforced: nobody is redirected here. New accounts land on
 * Home and see a banner, and this lives at its own route so Profile can send
 * someone back to it later.
 */
export function Welcome() {
  const query = useOnboarding()

  return (
    <QueryBoundary query={query} loading={<SkeletonGrid />}>
      {(state) => <Flow state={state} />}
    </QueryBoundary>
  )
}
