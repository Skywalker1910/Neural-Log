import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Camera, Check, RefreshCw, ScanLine, X } from 'lucide-react'

import { api } from '../../api/client'
import { scanLabel, type ScannedFood } from '../../api/assistant'
import { nutritionTableConfidence, prepareImage } from '../../lib/imageCapture'
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
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const detectorRef = useRef<HTMLCanvasElement | null>(null)
  const stableFramesRef = useRef(0)
  const scanningRef = useRef(false)

  const [stage, setStage] = useState<Stage>('capture')
  const [preview, setPreview] = useState<string | null>(null)
  const [food, setFood] = useState<ScannedFood | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [detecting, setDetecting] = useState(false)

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    stableFramesRef.current = 0
    setDetecting(false)
    setCameraOpen(false)
  }, [])

  function reset() {
    stopCamera()
    if (preview) URL.revokeObjectURL(preview)
    setPreview(null)
    setFood(null)
    setError(null)
    setStage('capture')
  }

  useEffect(() => () => stopCamera(), [stopCamera])

  const handleImage = useCallback(async (image: Blob | undefined, alreadyLocked = false) => {
    if (!image || (scanningRef.current && !alreadyLocked)) return
    scanningRef.current = true
    stopCamera()
    setError(null)
    setStage('reading')

    try {
      const prepared = await prepareImage(image)
      setPreview(prepared.previewUrl)
      setFood(await scanLabel(prepared.blob))
      setStage('review')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'That scan did not work.')
      setStage('capture')
    } finally {
      scanningRef.current = false
    }
  }, [stopCamera])

  async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Live camera capture is not available in this browser. Take a photo instead.')
      return
    }

    setError(null)
    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
      })
      setCameraOpen(true)
    } catch {
      setError('Camera access was not allowed. Take a photo instead, or allow camera access and retry.')
    }
  }

  const captureFrame = useCallback(async () => {
    const video = videoRef.current
    if (!video || !video.videoWidth || !video.videoHeight || scanningRef.current) return
    // Lock before `toBlob` resolves. Otherwise three positive detector frames
    // could each start their own upload on a slow phone.
    scanningRef.current = true
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const context = canvas.getContext('2d')
    if (!context) {
      scanningRef.current = false
      return
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height)
    const image = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92))
    if (image) {
      await handleImage(image, true)
    } else {
      scanningRef.current = false
    }
  }, [handleImage])

  useEffect(() => {
    const video = videoRef.current
    if (!cameraOpen || !video || !streamRef.current) return
    video.srcObject = streamRef.current
    void video.play().catch(() => {})

    const interval = window.setInterval(() => {
      if (!video.videoWidth || !video.videoHeight || scanningRef.current) return
      const canvas = detectorRef.current ?? document.createElement('canvas')
      detectorRef.current = canvas
      canvas.width = 240
      canvas.height = Math.max(120, Math.round((video.videoHeight / video.videoWidth) * 240))
      const context = canvas.getContext('2d', { willReadFrequently: true })
      if (!context) return
      context.drawImage(video, 0, 0, canvas.width, canvas.height)
      const confidence = nutritionTableConfidence(context.getImageData(0, 0, canvas.width, canvas.height))
      stableFramesRef.current = confidence >= 0.57 ? stableFramesRef.current + 1 : 0
      setDetecting(stableFramesRef.current > 0)
      if (stableFramesRef.current >= 3) {
        stableFramesRef.current = 0
        void captureFrame()
      }
    }, 420)

    return () => window.clearInterval(interval)
  }, [cameraOpen, captureFrame])

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
        // What makes the picker offer "2 scoops" rather than making somebody do
        // the 30 g multiplication in their head before typing it.
        is_countable: food.is_countable,
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
        onChange={(event) => void handleImage(event.target.files?.[0])}
      />

      {stage !== 'review' && (
        <div className="flex flex-col items-center gap-4 py-4 text-center">
          {cameraOpen ? (
            <div className="w-full overflow-hidden rounded-lg border border-line bg-black text-left">
              <div className="relative aspect-[4/3]">
                <video ref={videoRef} muted playsInline className="size-full object-cover" />
                <div className="pointer-events-none absolute inset-[12%] rounded-md border-2 border-brand/80 shadow-[0_0_0_999px_rgb(0_0_0_/_0.28)]" />
                <span className={cn(
                  'absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-1 text-meta',
                  detecting ? 'bg-success/90 text-black' : 'bg-black/70 text-ink',
                )}>
                  {detecting ? 'Table detected — hold steady' : 'Centre the nutrition table'}
                </span>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line p-2">
                <span className="text-meta text-ink-subtle">Captures automatically when the table is clear.</span>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" icon={Camera} onClick={() => void captureFrame()}>
                    Capture now
                  </Button>
                  <Button size="sm" variant="ghost" onClick={stopCamera}>Cancel</Button>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="flex size-16 items-center justify-center rounded-full bg-surface-raised">
                <ScanLine size={26} className="text-nutrition" aria-hidden />
              </div>
              <p className="max-w-sm text-meta text-ink-subtle">
                Point the camera at the whole table, including column headings. It captures once the
                label is steady and clear; nothing is saved until you review it.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                <Button variant="primary" icon={ScanLine} loading={stage === 'reading'} onClick={() => void startCamera()}>
                  Scan automatically
                </Button>
                <Button variant="secondary" icon={Camera} disabled={stage === 'reading'} onClick={() => fileRef.current?.click()}>
                  Take a photo
                </Button>
              </div>
            </>
          )}
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
              {food.serving_grams != null && (
                <span className="text-meta text-ink-subtle">
                  Serving: {food.serving_label
                    ? `1 ${food.serving_label} = ${food.serving_grams}${food.unit}`
                    : `${food.serving_grams}${food.unit}`}
                  {food.is_countable && ' · you can log these by the number'}
                </span>
              )}
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
