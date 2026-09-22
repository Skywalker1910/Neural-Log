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
 * The illustrations are drawn here and interpolate between two poses.
 *
 * ## Why per pattern and not per exercise
 *
 * A barbell bench press, a dumbbell floor press and a machine chest press are
 * one movement performed with three pieces of equipment. Seventeen patterns
 * cover a library of 136, and a new exercise inherits its animation by naming
 * the pattern it belongs to rather than needing anything drawn for it.
 *
 * These remain movement-pattern previews. Exercise-specific instructions carry
 * the setup and technique details.
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
  duration?: number
  className?: string
  progress?: number
  name?: string
  equipment?: string
}

export function ExerciseAnimation({
  pattern, size = 96, duration = 3.6, className, progress, name = '', equipment = '',
}: ExerciseAnimationProps) {
  const reduced = usePrefersReducedMotion()
  const gradientId = useId()
  let poses = pattern ? PATTERNS[pattern] : undefined
  const pushUp = /push.?up/i.test(name)
  const pulldown = /pulldown/i.test(name)
  if (pushUp) poses = [
    pose([17, 69], [29, 72], [36, 85], [28, 94], [58, 80], [75, 87], [92, 94]),
    pose([17, 48], [29, 52], [29, 74], [28, 94], [58, 68], [75, 82], [92, 94]),
  ]
  if (pulldown) poses = [
    pose([52, 31], [52, 43], [43, 28], [42, 9], [55, 69], [31, 72], [31, 94]),
    pose([52, 31], [52, 43], [35, 53], [40, 41], [55, 69], [31, 72], [31, 94]),
  ]
  if (!pattern || !poses) return null
  const [start, end] = poses
  const fraction = progress == null ? 0 : (1 - Math.cos(progress * Math.PI * 2)) / 2
  const current = (joint: keyof Pose, axis: number) => start[joint][axis] + (end[joint][axis] - start[joint][axis]) * fraction
  const moving = !reduced && progress == null
  const animateAttribute = (attribute: string, from: number, to: number) => moving
    ? <animate attributeName={attribute} dur={`${duration}s`} repeatCount="indefinite"
        values={`${from};${to};${from}`} calcMode="spline" keyTimes="0;0.5;1" keySplines="0.45 0 0.2 1;0.45 0 0.2 1" />
    : null
  const limb = (from: keyof Pose, to: keyof Pose, width: number, colour: string, offset = 0) => (
    <line key={`${from}-${to}-${offset}`} x1={current(from, 0) + offset} y1={current(from, 1)}
      x2={current(to, 0) + offset} y2={current(to, 1)} stroke={colour} strokeWidth={width} strokeLinecap="round">
      {animateAttribute('x1', start[from][0] + offset, end[from][0] + offset)}
      {animateAttribute('y1', start[from][1], end[from][1])}
      {animateAttribute('x2', start[to][0] + offset, end[to][0] + offset)}
      {animateAttribute('y2', start[to][1], end[to][1])}
    </line>
  )
  const weighted = /dumbbell|barbell|kettlebell/i.test(equipment) && !['squat', 'lunge'].includes(pattern)
  return <svg viewBox="0 0 110 106" width={size} height={size} className={cn('shrink-0', className)}
    role="img" aria-label={`${name || PATTERN_LABELS[pattern]} movement demonstration`}>
    <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="var(--color-fitness)" stopOpacity=".09" />
      <stop offset="100%" stopColor="var(--color-fitness)" stopOpacity=".02" />
    </linearGradient></defs>
    <rect width="110" height="106" rx="10" fill={`url(#${gradientId})`} />
    <ellipse cx="54" cy="98" rx="36" ry="3" fill="#7f8a88" opacity=".2" />
    <path d="M10 99H100" stroke="#8c9692" strokeWidth=".6" opacity=".6" />
    {LYING.has(pattern) && !pushUp && <path d="M17 65H75M29 65V94M65 65V94" fill="none" stroke="#758681" strokeWidth="3" strokeLinecap="round" />}
    {pulldown && <path d="M29 75H66M57 75V97M75 8V97M32 8H75" stroke="#758681" strokeWidth="2" fill="none" />}
    {pattern === 'vertical-pull' && !pulldown && <path d="M28 8H72" stroke="#758681" strokeWidth="3" />}
    <g opacity=".42">
      {limb('shoulder', 'elbow', 5, '#ba937b', 6)}
      {limb('elbow', 'hand', 4, '#d2af94', 6)}
      {pattern === 'lunge' ? <path d="M55 61L76 80L86 94" stroke="#637b80" strokeWidth="7" fill="none" strokeLinecap="round" /> : <>
        {limb('hip', 'knee', 7, '#637b80', 7)}
        {limb('knee', 'foot', 5, '#637b80', 7)}
      </>}
    </g>
    {SEGMENTS.map(([from, to]) => limb(from, to, from === 'shoulder' && to === 'hip' ? 13 : from === 'hip' ? 8 : 5.5,
      to === 'hip' ? '#4c7875' : from === 'hip' || from === 'knee' ? '#425a6b' : '#d2ac8d'))}
    <circle cx={current('head', 0)} cy={current('head', 1)} r="6.5" fill="#d2ac8d">
      {animateAttribute('cx', start.head[0], end.head[0])}{animateAttribute('cy', start.head[1], end.head[1])}
    </circle>
    <circle cx={current('elbow', 0)} cy={current('elbow', 1)} r="1.7" fill="#f8e3c3">
      {animateAttribute('cx', start.elbow[0], end.elbow[0])}{animateAttribute('cy', start.elbow[1], end.elbow[1])}
    </circle>
    {weighted && <g transform={`translate(${current('hand', 0)} ${current('hand', 1)})`}>
      {moving && <animateTransform attributeName="transform" type="translate" dur={`${duration}s`}
        values={`${start.hand.join(' ')};${end.hand.join(' ')};${start.hand.join(' ')}`} repeatCount="indefinite"
        calcMode="spline" keyTimes="0;0.5;1" keySplines="0.45 0 0.2 1;0.45 0 0.2 1" />}
      <path d="M-9 0H9M-8-4V4M8-4V4" stroke="#59615f" strokeWidth="3" strokeLinecap="round" />
    </g>}
    <path d={`M${start.hand[0]} ${start.hand[1]}L${end.hand[0]} ${end.hand[1]}`}
      stroke="#ad8164" strokeWidth="1" strokeDasharray="2 3" opacity=".5" />
  </svg>
}
