import { useId } from 'react'

import { cn } from '../../lib/cn'
import { PATTERN_LABELS } from '../../lib/movementPatterns'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'

/**
 * An exercise, animated.
 *
 * ## Why these are drawn rather than fetched
 *
 * The obvious way to show a movement is the illustrated demonstration everyone
 * has seen on a gym poster. Those belong to whoever drew them, and the
 * third-party exercise GIF libraries are the same pictures with the same owner.
 * Shipping them would be someone else's copyright sitting in our repository.
 *
 * So they are stick figures, drawn here, animating between two poses.
 *
 * ## Why per pattern and not per exercise
 *
 * A barbell bench press, a dumbbell floor press and a machine chest press are
 * one movement performed with three pieces of equipment. Seventeen patterns
 * cover a library of 136, and a new exercise inherits its animation by naming
 * the pattern it belongs to rather than needing anything drawn for it.
 *
 * The honest limit of that: the animation shows the *shape* of the movement, not
 * the equipment. It is a reminder of what a hip hinge looks like, not a
 * substitute for being coached through a deadlift. The instructions underneath
 * carry the detail.
 */

/** A figure, as joint coordinates in a 100x100 box. */
interface Pose {
  head: [number, number]
  shoulder: [number, number]
  elbow: [number, number]
  hand: [number, number]
  hip: [number, number]
  knee: [number, number]
  foot: [number, number]
}

const pose = (
  head: [number, number], shoulder: [number, number], elbow: [number, number],
  hand: [number, number], hip: [number, number], knee: [number, number],
  foot: [number, number],
): Pose => ({ head, shoulder, elbow, hand, hip, knee, foot })

/**
 * Each pattern is two poses: the start of the rep and the end of it. The figure
 * travels between them and back, which is what a repetition is.
 *
 * Coordinates are eyeballed rather than derived - the point is recognition, and
 * a hinge has to *look* like a hinge at 64 pixels more than it has to be
 * anatomically sound at 400.
 */
const PATTERNS: Record<string, [Pose, Pose]> = {
  // Lying, pressing away from the chest. Drawn side-on, head to the left.
  'horizontal-press': [
    pose([24, 58], [36, 60], [42, 48], [40, 36], [64, 60], [74, 74], [84, 88]),
    pose([24, 58], [36, 60], [38, 44], [38, 28], [64, 60], [74, 74], [84, 88]),
  ],
  // Standing, pressing overhead.
  'vertical-press': [
    pose([50, 20], [50, 32], [40, 42], [44, 30], [50, 56], [48, 76], [48, 94]),
    pose([50, 20], [50, 32], [48, 20], [48, 6], [50, 56], [48, 76], [48, 94]),
  ],
  // Hinged over, pulling to the ribs.
  'horizontal-pull': [
    pose([26, 36], [38, 40], [40, 58], [42, 74], [62, 48], [64, 72], [62, 94]),
    pose([26, 36], [38, 40], [46, 50], [44, 40], [62, 48], [64, 72], [62, 94]),
  ],
  // Hanging or pulling down from overhead.
  'vertical-pull': [
    pose([50, 34], [50, 44], [48, 26], [46, 10], [50, 64], [50, 82], [50, 96]),
    pose([50, 22], [50, 34], [40, 26], [46, 12], [50, 56], [52, 76], [52, 94]),
  ],
  squat: [
    pose([50, 18], [50, 30], [44, 42], [42, 52], [50, 54], [50, 74], [50, 94]),
    pose([44, 36], [46, 48], [40, 58], [38, 66], [52, 70], [38, 80], [50, 94]),
  ],
  hinge: [
    pose([50, 18], [50, 30], [48, 44], [48, 56], [50, 56], [50, 76], [50, 94]),
    pose([26, 40], [36, 44], [40, 58], [42, 72], [58, 54], [56, 76], [54, 94]),
  ],
  lunge: [
    pose([50, 18], [50, 30], [44, 44], [44, 56], [50, 56], [50, 76], [50, 94]),
    pose([48, 26], [48, 38], [42, 50], [42, 62], [50, 62], [32, 78], [30, 94]),
  ],
  curl: [
    pose([50, 20], [50, 32], [50, 50], [50, 68], [50, 58], [50, 78], [50, 94]),
    pose([50, 20], [50, 32], [50, 50], [40, 36], [50, 58], [50, 78], [50, 94]),
  ],
  extension: [
    pose([50, 20], [50, 32], [48, 24], [38, 34], [50, 58], [50, 78], [50, 94]),
    pose([50, 20], [50, 32], [48, 24], [48, 8], [50, 58], [50, 78], [50, 94]),
  ],
  raise: [
    pose([50, 20], [50, 32], [50, 48], [50, 64], [50, 58], [50, 78], [50, 94]),
    pose([50, 20], [50, 32], [32, 34], [16, 32], [50, 58], [50, 78], [50, 94]),
  ],
  fly: [
    pose([50, 22], [50, 34], [38, 38], [26, 38], [50, 58], [50, 78], [50, 94]),
    pose([50, 22], [50, 34], [44, 42], [50, 46], [50, 58], [50, 78], [50, 94]),
  ],
  'calf-raise': [
    pose([50, 22], [50, 34], [46, 48], [44, 60], [50, 58], [50, 78], [50, 94]),
    pose([50, 14], [50, 26], [46, 40], [44, 52], [50, 50], [50, 72], [50, 90]),
  ],
  'core-flexion': [
    pose([22, 58], [34, 60], [28, 50], [22, 44], [62, 60], [74, 74], [86, 86]),
    pose([36, 44], [44, 54], [38, 44], [32, 38], [62, 60], [68, 66], [74, 52]),
  ],
  'core-brace': [
    pose([20, 50], [32, 54], [30, 70], [28, 84], [60, 62], [76, 74], [90, 84]),
    pose([20, 52], [32, 56], [30, 72], [28, 86], [60, 64], [76, 76], [90, 86]),
  ],
  'core-rotation': [
    pose([50, 30], [50, 42], [38, 48], [28, 46], [50, 64], [56, 80], [50, 94]),
    pose([50, 30], [50, 42], [62, 48], [72, 46], [50, 64], [44, 80], [50, 94]),
  ],
  carry: [
    pose([50, 20], [50, 32], [50, 50], [50, 66], [50, 58], [48, 78], [46, 94]),
    pose([50, 22], [50, 34], [50, 52], [50, 68], [50, 60], [54, 78], [56, 94]),
  ],
  'cardio-cyclic': [
    pose([50, 18], [50, 30], [38, 38], [30, 48], [50, 56], [38, 74], [30, 92]),
    pose([50, 18], [50, 30], [62, 38], [70, 48], [50, 56], [62, 74], [70, 92]),
  ],
  mobility: [
    pose([50, 22], [50, 34], [42, 46], [36, 58], [50, 58], [48, 78], [46, 94]),
    pose([40, 30], [44, 40], [30, 44], [18, 44], [52, 60], [46, 78], [42, 94]),
  ],
}

/**
 * Patterns performed lying down. Without something under the figure a bench
 * press reads as a diagonal slash at 44 pixels - the pose is right, but there is
 * nothing to tell you the person is lying on a bench rather than falling over.
 */
const LYING = new Set(['horizontal-press', 'core-flexion'])

const SEGMENTS: [keyof Pose, keyof Pose][] = [
  ['shoulder', 'elbow'],
  ['elbow', 'hand'],
  ['shoulder', 'hip'],
  ['hip', 'knee'],
  ['knee', 'foot'],
]

interface ExerciseAnimationProps {
  pattern: string | null | undefined
  size?: number
  /** Seconds for one full repetition, out and back. */
  duration?: number
  className?: string
}

export function ExerciseAnimation({
  pattern,
  size = 96,
  duration = 2.4,
  className,
}: ExerciseAnimationProps) {
  const reduced = usePrefersReducedMotion()
  const gradientId = useId()

  const poses = pattern ? PATTERNS[pattern] : undefined
  // Nothing rather than a wrong figure: an exercise with no pattern, or one
  // naming a pattern nobody has drawn yet, simply shows no animation.
  if (!pattern || !poses) return null

  const [start, end] = poses
  // Out and back, so the figure returns to where a rep began rather than
  // snapping home.
  const frames = (from: [number, number], to: [number, number]) =>
    `${from[0]},${from[1]}; ${to[0]},${to[1]}; ${from[0]},${from[1]}`

  const stroke = 'var(--color-fitness)'

  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={cn('shrink-0', className)}
      role="img"
      aria-label={`${PATTERN_LABELS[pattern] ?? 'Movement'} animation`}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--color-fitness)" stopOpacity={0.14} />
          <stop offset="100%" stopColor="var(--color-fitness)" stopOpacity={0} />
        </linearGradient>
      </defs>

      <rect x="0" y="0" width="100" height="100" rx="12" fill={`url(#${gradientId})`} />

      {/* Ground line, so a standing figure reads as standing. */}
      <line x1="10" y1="96" x2="90" y2="96" stroke="var(--color-line-strong)" strokeWidth="1.5" />

      {LYING.has(pattern) && (
        <>
          <line
            x1="18" y1="64" x2="74" y2="64"
            stroke="var(--color-line-strong)" strokeWidth="4" strokeLinecap="round"
          />
          <line x1="30" y1="64" x2="30" y2="84" stroke="var(--color-line-strong)" strokeWidth="2.5" />
          <line x1="64" y1="64" x2="64" y2="84" stroke="var(--color-line-strong)" strokeWidth="2.5" />
        </>
      )}

      {SEGMENTS.map(([from, to]) => (
        <line
          key={`${from}-${to}`}
          x1={start[from][0]} y1={start[from][1]}
          x2={start[to][0]} y2={start[to][1]}
          stroke={stroke}
          strokeWidth="4"
          strokeLinecap="round"
        >
          {/*
            SMIL rather than CSS: these are element *attributes*, which CSS
            cannot animate, and doing it in JS would mean a render loop per
            figure on a page showing a dozen of them.

            Under reduced motion the <animate> elements are simply not rendered,
            so the figure holds the starting pose. The shape still reads.
          */}
          {!reduced && (
            <>
              <animate
                attributeName="x1" dur={`${duration}s`} repeatCount="indefinite"
                values={`${start[from][0]}; ${end[from][0]}; ${start[from][0]}`}
                calcMode="spline" keyTimes="0; 0.5; 1"
                keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
              />
              <animate
                attributeName="y1" dur={`${duration}s`} repeatCount="indefinite"
                values={`${start[from][1]}; ${end[from][1]}; ${start[from][1]}`}
                calcMode="spline" keyTimes="0; 0.5; 1"
                keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
              />
              <animate
                attributeName="x2" dur={`${duration}s`} repeatCount="indefinite"
                values={`${start[to][0]}; ${end[to][0]}; ${start[to][0]}`}
                calcMode="spline" keyTimes="0; 0.5; 1"
                keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
              />
              <animate
                attributeName="y2" dur={`${duration}s`} repeatCount="indefinite"
                values={`${start[to][1]}; ${end[to][1]}; ${start[to][1]}`}
                calcMode="spline" keyTimes="0; 0.5; 1"
                keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
              />
            </>
          )}
        </line>
      ))}

      <circle cx={start.head[0]} cy={start.head[1]} r="7" fill={stroke}>
        {!reduced && (
          <>
            <animate
              attributeName="cx" dur={`${duration}s`} repeatCount="indefinite"
              values={frames(start.head, end.head).split(';').map((p) => p.trim().split(',')[0]).join(';')}
              calcMode="spline" keyTimes="0; 0.5; 1"
              keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
            />
            <animate
              attributeName="cy" dur={`${duration}s`} repeatCount="indefinite"
              values={frames(start.head, end.head).split(';').map((p) => p.trim().split(',')[1]).join(';')}
              calcMode="spline" keyTimes="0; 0.5; 1"
              keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
            />
          </>
        )}
      </circle>
    </svg>
  )
}
