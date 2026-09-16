import type { AttributeScore } from '../api/types'
import type { Accent } from '../navigation'

/**
 * Shared attribute presentation. Extracted in R9 because Profile shows the same
 * eight rings as Home, and two copies of this mapping is how the same attribute
 * ends up a different colour on two pages.
 */

/**
 * Eight attributes over seven accent tokens. Strength and Stamina deliberately
 * share the fitness accent - they are both physical, and inventing an eighth
 * colour for the sake of uniqueness would weaken the category language the rest
 * of the app uses.
 */
export const ATTRIBUTE_ACCENT: Record<string, Accent> = {
  Discipline: 'discipline',
  Knowledge: 'learning',
  Strength: 'fitness',
  Stamina: 'fitness',
  Agility: 'lifestyle',
  Recovery: 'recovery',
  Consistency: 'goals',
  Focus: 'brand',
}

/**
 * Why an attribute has no number, in the user's words.
 *
 * Returns undefined for an active attribute - there is nothing to explain when
 * the score is real. Every other branch exists so "no data" never renders as a
 * zero, which is the dishonesty the whole scoring engine is built to avoid.
 */
export function attributeHint(attribute: AttributeScore): string | undefined {
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
