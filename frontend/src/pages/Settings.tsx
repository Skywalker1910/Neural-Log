import { useState } from 'react'
import { KeyRound, Settings as SettingsIcon, SlidersHorizontal } from 'lucide-react'

import { ApiError, api } from '../api/client'
import { useOnboarding, useProfile, useSaveProfile } from '../api/queries'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Field, TextInput } from '../components/ui/Field'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'

/**
 * Targets you can set by hand.
 *
 * Every one of these is optional, and leaving it blank is the better default:
 * `resolve_targets` derives an estimate from your baselines and reports
 * `sources: estimated`, which the UI can be honest about. A number typed here
 * becomes `set` and is never overruled by an estimate - so the badge beside each
 * field is load-bearing, not decoration.
 */
const TARGETS: { key: string; label: string; unit: string; hint: string; source: string }[] = [
  { key: 'calorie_target', label: 'Calories', unit: 'kcal', source: 'calories',
    hint: 'Blank uses your daily energy estimate, adjusted for your goal.' },
  { key: 'protein_target_g', label: 'Protein', unit: 'g', source: 'protein',
    hint: 'Blank uses grams per kg of body weight, higher on a cut.' },
  { key: 'carb_target_g', label: 'Carbohydrate', unit: 'g', source: 'carbs',
    hint: 'Blank uses whatever the calorie budget has left.' },
  { key: 'fat_target_g', label: 'Fat', unit: 'g', source: 'fat',
    hint: 'Blank uses a quarter of your calories.' },
  { key: 'water_target_ml', label: 'Water', unit: 'ml', source: 'water',
    hint: 'Does not depend on body composition, so this one has a fixed default.' },
  { key: 'step_target', label: 'Steps', unit: '', source: 'steps',
    hint: 'Feeds Stamina over a trailing window.' },
  { key: 'sleep_target_minutes', label: 'Sleep', unit: 'min', source: 'sleep',
    hint: 'Feeds Recovery. Duration only — the schedule lives on your profile.' },
  { key: 'weekly_study_minutes', label: 'Weekly study', unit: 'min', source: 'study',
    hint: 'Feeds Knowledge.' },
]

function TargetSettings() {
  const query = useProfile()
  const save = useSaveProfile()
  const [draft, setDraft] = useState<Record<string, string>>({})

  return (
    <QueryBoundary query={query} loading={<SkeletonGrid />}>
      {(data) => {
        const dirty = Object.keys(draft).length > 0

        return (
          <Card
            title="Targets"
            subtitle="What the scoring engine measures your days against"
            icon={SlidersHorizontal}
            accent="discipline"
            action={
              <Button
                variant="primary"
                size="sm"
                disabled={!dirty}
                loading={save.isPending}
                onClick={() => {
                  const payload: Record<string, number | null> = {}
                  for (const [key, value] of Object.entries(draft)) {
                    payload[key] = value === '' ? null : Number(value)
                  }
                  save.mutate(payload, { onSuccess: () => setDraft({}) })
                }}
              >
                Save
              </Button>
            }
          >
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {TARGETS.map((target) => {
                const stored = (data.profile as Record<string, unknown> | null)?.[target.key]
                const value = draft[target.key] ?? (stored == null ? '' : String(stored))
                const source = data.targets.sources?.[target.source]

                return (
                  <Field
                    key={target.key}
                    label={target.label}
                    hint={
                      <span className="flex flex-wrap items-center gap-1.5">
                        {source === 'set' ? (
                          <Badge tone="success">Set by you</Badge>
                        ) : source === 'estimated' ? (
                          <Badge tone="neutral">Estimated</Badge>
                        ) : null}
                        <span>{target.hint}</span>
                      </span>
                    }
                  >
                    {(id) => (
                      <TextInput
                        id={id}
                        type="number"
                        inputMode="numeric"
                        placeholder={target.unit ? `— ${target.unit}` : '—'}
                        value={value}
                        onChange={(event) =>
                          setDraft((current) => ({ ...current, [target.key]: event.target.value }))
                        }
                      />
                    )}
                  </Field>
                )
              })}
            </div>

            <p className="mt-4 text-meta text-ink-subtle">
              Changing a target re-judges your history, not just today — a new calorie target
              changes what every past day was aiming at.
            </p>

            {save.isError && (
              <p className="mt-3 text-label text-danger">
                Could not save those targets. Your edits are still here — try again.
              </p>
            )}
          </Card>
        )
      }}
    </QueryBoundary>
  )
}

function PasswordSettings() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [status, setStatus] = useState<{ tone: 'ok' | 'error'; message: string } | null>(null)
  const [saving, setSaving] = useState(false)

  const submit = async () => {
    setStatus(null)

    // Checked here as well as on the server, because a mismatch is the one error
    // the client can be certain about, and a round trip to be told you typed it
    // twice differently is a poor use of anyone's time.
    if (next !== confirm) {
      setStatus({ tone: 'error', message: 'The new passwords do not match.' })
      return
    }

    setSaving(true)
    try {
      await api.post('/api/user/reset-password', {
        current_password: current,
        new_password: next,
      })
      setStatus({ tone: 'ok', message: 'Password changed.' })
      setCurrent('')
      setNext('')
      setConfirm('')
    } catch (error) {
      setStatus({
        tone: 'error',
        message: error instanceof ApiError ? error.message : 'Could not change your password.',
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card
      title="Password"
      subtitle="At least six characters"
      icon={KeyRound}
      accent="brand"
      action={
        <Button
          variant="primary"
          size="sm"
          loading={saving}
          disabled={!current || !next || !confirm}
          onClick={submit}
        >
          Change
        </Button>
      }
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Current password">
          {(id) => (
            <TextInput
              id={id} type="password" autoComplete="current-password"
              value={current} onChange={(event) => setCurrent(event.target.value)}
            />
          )}
        </Field>
        <Field label="New password">
          {(id) => (
            <TextInput
              id={id} type="password" autoComplete="new-password" minLength={6}
              value={next} onChange={(event) => setNext(event.target.value)}
            />
          )}
        </Field>
        <Field label="Confirm new password">
          {(id) => (
            <TextInput
              id={id} type="password" autoComplete="new-password" minLength={6}
              value={confirm} onChange={(event) => setConfirm(event.target.value)}
            />
          )}
        </Field>
      </div>

      {status && (
        <p className={status.tone === 'ok' ? 'mt-3 text-label text-success' : 'mt-3 text-label text-danger'}>
          {status.message}
        </p>
      )}
    </Card>
  )
}

export function Settings() {
  const onboarding = useOnboarding()

  return (
    <>
      <PageHeader
        title="Settings"
        description="Targets, account, and the classic dashboard."
        icon={SettingsIcon}
        accent="brand"
      />

      <RevealGroup className="flex flex-col gap-4" step={0.05}>
        <Reveal><TargetSettings /></Reveal>
        <Reveal><PasswordSettings /></Reveal>

        <Reveal>
          <Card title="Elsewhere" subtitle="Things that still live on the classic dashboard">
            <ul className="flex flex-col gap-2 text-label">
              <li>
                <a href="/api/export/excel" className="text-brand underline underline-offset-2">
                  Export everything to Excel
                </a>
              </li>
              <li>
                <a href="/classic" className="text-brand underline underline-offset-2">
                  Open the classic dashboard
                </a>
                <span className="text-ink-subtle"> — milestone insights and admin</span>
              </li>
              {onboarding.data && !onboarding.data.completed && (
                <li>
                  <a href="/welcome" className="text-brand underline underline-offset-2">
                    Finish setting up
                  </a>
                  <span className="text-ink-subtle">
                    {' '}— {onboarding.data.steps.length - onboarding.data.step} steps left
                  </span>
                </li>
              )}
            </ul>
          </Card>
        </Reveal>
      </RevealGroup>
    </>
  )
}
