import type { Food } from '../api/types'

/**
 * How to show an amount of this food.
 *
 * Everything is stored in grams - that is what the per-100g macros need - but
 * "240 g of coffee" is a question nobody can answer. Liquids are labelled ml,
 * taking 1 ml as 1 g, which holds to about 3% for water-based drinks and milk.
 * Oils deliberately keep grams: at 0.92 g/ml the conversion would be off by 8%,
 * and a spoon is how they get measured anyway.
 */
export function unitOf(food: { unit?: Food['unit'] } | null | undefined): 'g' | 'ml' {
  // Grams when the unit is missing: a custom food added before units existed,
  // and an entry from an older client, both read as grams - which is what they
  // always were.
  return food?.unit === 'ml' ? 'ml' : 'g'
}

/** "240 ml" / "150 g". */
export function amountLabel(
  amount: number | string,
  food: { unit?: Food['unit'] } | null | undefined,
): string {
  return `${amount} ${unitOf(food)}`
}
