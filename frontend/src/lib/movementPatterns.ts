/**
 * The movement-pattern vocabulary, kept apart from the component that draws it.
 *
 * A barbell bench press, a dumbbell floor press and a machine chest press are one
 * movement performed with three pieces of equipment, so the animations are keyed
 * to the pattern rather than to the exercise. Seventeen of these cover a library
 * of 136, and a new exercise inherits its animation by naming one.
 */
export const PATTERN_LABELS: Record<string, string> = {
  'horizontal-press': 'Horizontal press',
  'vertical-press': 'Vertical press',
  'horizontal-pull': 'Horizontal pull',
  'vertical-pull': 'Vertical pull',
  squat: 'Squat',
  hinge: 'Hip hinge',
  lunge: 'Lunge',
  curl: 'Curl',
  extension: 'Extension',
  raise: 'Raise',
  fly: 'Fly',
  'calf-raise': 'Calf raise',
  'core-flexion': 'Trunk flexion',
  'core-brace': 'Brace',
  'core-rotation': 'Rotation',
  carry: 'Loaded carry',
  'cardio-cyclic': 'Cyclic effort',
  mobility: 'Mobility',
}

export function patternLabel(pattern: string | null | undefined): string | null {
  return pattern ? PATTERN_LABELS[pattern] ?? null : null
}
