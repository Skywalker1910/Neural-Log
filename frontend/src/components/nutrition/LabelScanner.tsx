import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Camera, Check, RefreshCw, X } from 'lucide-react'

import { api } from '../../api/client'
import { scanLabel, type ScannedFood } from '../../api/assistant'
import { prepareImage } from '../../lib/imageCapture'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { cn } from '../../lib/cn'

/**
 * Photograph a nutrition panel, check it, keep it.
 *
 * The catalogue ships 248 foods and does not have the oat milk you actually buy.
 * Typing a packet in by hand means squinting at six numbers and getting the
 * units wrong on at least one, which is exactly the job to hand to a camera.
 *
 * ## Why there is still a form
 *
 * Because the model reads small print off a curved, shiny surface under kitchen
 * lighting, and sometimes it gets a digit wrong. The scan fills the form; the
 * person checks it. Two things make that check possible rather than theatre:
 *
 * The **conversion note** says what arithmetic happened. A US label is per
 * serving, so its numbers were multiplied by something to reach per-100g, and
 * "x3.33 from a 30 g serving" is checkable where "400 kcal" is not.
 *
 * The **unreadable list** marks fields the model could not see, so they arrive
 * flagged rather than as a confident zero. Zero fibre and unknown fibre are
 * different claims, and only one of them should end up in somebody's intake.
 */

interface LabelScannerProps {
  open: boolean
  onClose: () => void
  onSaved?: (food: { id: number; name: string }) => void
}

type Stage = 'capture' | 'reading' | 'review'

const FIELDS: { key: keyof ScannedFood; label: string; suffix: string }[] = [
  { key: 'kcal_per_100g', label: 'Calories', suffix: 'kcal' },
  { key: 'protein_per_100g', label: 'Protein', suffix: 'g' },
  { key: 'carbs_per_100g', label: 'Carbs', suffix: 'g' },
  { key: 'fat_per_100g', label: 'Fat', suffix: 'g' },
  { key: 'fibre_per_100g', label: 'Fibre', suffix: 'g' },
]

/** `fibre_per_100g` -> `fibre`, to match what the server flags as unreadable. */
function shortName(key: string): string {
  return key.replace('_per_100g', '')
}

export function LabelScanner({ open, onClose, onSaved }: LabelScannerProps) {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)

  const [stage, setStage] = useState<Stage>('capture')
  const [preview, setPreview] = useState<string | null>(null)
  const [food, setFood] = useState<ScannedFood | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  function reset() {
    if (preview) URL.revokeObjectURL(preview)
    setPreview(null)
    setFood(null)
    setError(null)
    setStage('capture')
  }

  async function handleFile(file: File | undefined) {
    if (!file) return
    setError(null)
    setStage('reading')

    try {
      const image = await prepareImage(file)
      setPreview(image.previewUrl)
      setFood(await scanLabel(image.blob))
      setStage('review')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'That scan did not work.')
      setStage('capture')
    }
  }

  async function save() {
    if (!food) return
    setSaving(true)
    setError(null)
    try {
      const saved = await api.post<{ id: number; name: string }>('/api/foods', {
        name: food.name,
        category: food.category,
        unit: food.unit,
        kcal_per_100g: food.kcal_per_100g,
        protein_per_100g: food.protein_per_100g,
        carbs_per_100g: food.carbs_per_100g,
        fat_per_100g: food.fat_per_100g,
        fibre_per_100g: food.fibre_per_100g,
        serving_name: food.serving_name,
        serving_grams: food.serving_grams,
      })
      // The catalogue is cached and the recipe builder reads it, so a new food
      // has to invalidate before the person goes looking for it.
      await queryClient.invalidateQueries({ queryKey: ['foods'] })
      onSaved?.(saved)
      reset()
      onClose()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not save that.')
    } finally {
      setSaving(false)
    }
  }

  function update(key: keyof ScannedFood, raw: string) {
    setFood((current) =>
      current ? { ...current, [key]: raw === '' ? 0 : Number(raw) || 0 } : current,
    )
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        reset()
        onClose()
      }}
      title="Scan a nutrition label"
      description="Photograph the panel on the back of the pack. Nothing is saved until you confirm it."
    >
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        // Opens the rear camera on a phone and a file picker on a laptop, with
        // no permission prompt and no getUserMedia lifecycle to manage.
        capture="environment"
        className="sr-only"
        onChange={(event) => void handleFile(event.target.files?.[0])}
      />

      {stage !== 'review' && (
        <div className="flex flex-col items-center gap-4 py-4 text-center">
          <div className="flex size-16 items-center justify-center rounded-full bg-surface-raised">
            <Camera size={26} className="text-nutrition" aria-hidden />
          </div>
          <p className="max-w-sm text-meta text-ink-subtle">
            Get the whole table in frame, including the column headings — they say
            whether the numbers are per 100&nbsp;g or per serving, and that changes
            everything.
          </p>
          <Button
            variant="primary"
            icon={Camera}
            loading={stage === 'reading'}
            onClick={() => fileRef.current?.click()}
          >
            {stage === 'reading' ? 'Reading the label' : 'Take a photo'}
          </Button>
        </div>
      )}

      {stage === 'review' && food && (
        <div className="flex flex-col gap-4">
          <div className="flex min-w-0 gap-3">
            {preview && (
              <img
                src={preview}
                alt="The label you photographed"
                className="size-24 shrink-0 rounded-md border border-line object-cover"
              />
            )}
            <label className="flex min-w-0 flex-1 flex-col gap-1">
              <span className="text-caption uppercase tracking-wide text-ink-subtle">
                Product
              </span>
              <input
                value={food.name}
                onChange={(event) =>
                  setFood((current) => (current ? { ...current, name: event.target.value } : current))
                }
                className="w-full min-w-0 rounded-md border border-line bg-surface-base px-2 py-1.5 text-label text-ink outline-none focus:border-brand"
              />
              <span className="text-meta text-ink-subtle">
                Per 100 {food.unit} · {food.conversion_note}
              </span>
            </label>
          </div>

          {food.unreadable.length > 0 && (
            <p className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/10 p-3 text-meta text-ink">
              <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" aria-hidden />
              <span>
                Could not read {food.unreadable.join(', ')} — those are showing as zero.
                Fill them in or leave them if the pack does not list them.
              </span>
            </p>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {FIELDS.map((field) => {
              const flagged = food.unreadable.includes(shortName(field.key as string))
              return (
                <label key={field.key as string} className="flex min-w-0 flex-col gap-1">
                  <span
                    className={cn(
                      'text-caption uppercase tracking-wide',
                      flagged ? 'text-warning' : 'text-ink-subtle',
                    )}
                  >
                    {field.label}
                  </span>
                  <span className="flex items-baseline gap-1">
                    <input
                      inputMode="decimal"
                      value={String(food[field.key] ?? '')}
                      onChange={(event) => update(field.key, event.target.value)}
                      className={cn(
                        'tabular w-full min-w-0 rounded-md border bg-surface-base px-2 py-1.5',
                        'text-label text-ink outline-none focus:border-brand',
                        flagged ? 'border-warning/50' : 'border-line',
                      )}
                    />
                    <span className="shrink-0 text-meta text-ink-subtle">{field.suffix}</span>
                  </span>
                </label>
              )
            })}
          </div>

          {error && <p className="text-label text-danger">{error}</p>}

          <div className="flex flex-wrap gap-2">
            <Button variant="primary" icon={Check} loading={saving} onClick={() => void save()}>
              Save to my foods
            </Button>
            <Button variant="secondary" icon={RefreshCw} onClick={reset} disabled={saving}>
              Retake
            </Button>
            <Button variant="ghost" icon={X} onClick={() => { reset(); onClose() }} disabled={saving}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {stage !== 'review' && error && (
        <p className="mt-2 text-label text-danger">{error}</p>
      )}
    </Modal>
  )
}
