import type { Food } from '../api/types'

/**
 * How an amount of food is entered and shown.
 *
 * Everything is stored in grams - that is what the per-100g macros need - but
 * grams are frequently not how you measured it. You used a cup of chickpeas, ate
 * two eggs, poured a mug of coffee. Converting in your head before typing is the
 * app making you do its job.
 *
 * So these are entry units. Each one converts to grams on the way in and back on
 * the way out, and a unit is only offered when the conversion for that food is
 * actually known.
 */

export type MeasureKey = 'g' | 'ml' | 'oz' | 'cup' | 'piece' | 'serving'

export interface Measure {
  key: MeasureKey
  label: string
  /** Grams in one of this unit, for this food. */
  grams: number
  /** Sensible starting amount when you switch to it. */
  step: number
}

/** 1 oz = 28.3495 g, exactly, by definition. */
const GRAMS_PER_OZ = 28.349523125

/**
 * Liquids read in millilitres, taking 1 ml as 1 g. True to about 3% for
 * water-based drinks and milk - well inside the error already in "one mug".
 * Oils keep grams: at 0.92 g/ml the conversion would be off by 8%, and a spoon
 * is how they get measured anyway.
 */
export function unitOf(food: { unit?: Food['unit'] } | null | undefined): 'g' | 'ml' {
  return food?.unit === 'ml' ? 'ml' : 'g'
}

/** "240 ml" / "150 g". */
export function amountLabel(
  amount: number | string,
  food: { unit?: Food['unit'] } | null | undefined,
): string {
  return `${amount} ${unitOf(food)}`
}

/**
 * Every way this particular food can be entered, best first.
 *
 * Cups appear only when `grams_per_cup` is set. A cup is a volume and grams are
 * a mass, so the factor depends on what is in the cup - 240 g of water, about
 * 164 g of cooked chickpeas, about 125 g of flour. Offering cups everywhere with
 * one hard-coded number would silently misreport half the library, so a food
 * without a known cup weight simply is not offered one.
 */
export function measuresFor(food: Food | null | undefined): Measure[] {
  if (!food) return []

  const out: Measure[] = []
  const base = unitOf(food)

  if (food.is_countable && food.serving_grams) {
    out.push({
      key: 'piece',
      // "1 egg" -> "egg", so the counter reads "2 egg" rather than "2 1 egg".
      label: (food.serving_name ?? 'piece').replace(/^1\s+/, ''),
      grams: food.serving_grams,
      step: 1,
    })
  }

  // A recipe is measured in the portions it was cooked into.
  if (food.source === 'recipe' && food.serving_grams) {
    out.push({ key: 'serving', label: 'serving', grams: food.serving_grams, step: 1 })
  }

  out.push({
    key: base,
    label: base,
    grams: 1,
    step: base === 'ml' ? 50 : 10,
  })

  if (food.grams_per_cup) {
    out.push({ key: 'cup', label: 'cup', grams: food.grams_per_cup, step: 0.25 })
  }

  out.push({ key: 'oz', label: 'oz', grams: GRAMS_PER_OZ, step: 1 })

  return out
}

/** Amount in a unit -> grams, which is the only thing the server stores. */
export function toGrams(amount: number, measure: Measure | undefined): number {
  if (!measure) return amount
  return Math.round(amount * measure.grams * 10) / 10
}

/** Grams -> amount in a unit, for prefilling when the unit changes. */
export function fromGrams(grams: number, measure: Measure | undefined): number {
  if (!measure || !measure.grams) return grams
  const value = grams / measure.grams
  // Whole numbers for pieces and servings; a quarter is the useful precision
  // for cups; one decimal for everything else.
  if (measure.key === 'piece' || measure.key === 'serving') return Math.max(1, Math.round(value))
  if (measure.key === 'cup') return Math.round(value * 4) / 4
  return Math.round(value * 10) / 10
}

/** "2 eggs · 100 g" - what was entered, and what it came to. */
export function measureSummary(amount: number, measure: Measure | undefined): string | null {
  if (!measure || measure.key === 'g' || measure.key === 'ml') return null
  const grams = toGrams(amount, measure)
  const plural = amount === 1 || measure.key === 'cup' ? measure.label : `${measure.label}s`
  return `${amount} ${plural} · ${grams} g`
}
