/**
 * Pounds and kilograms, in one place, for the same reason `scoring/units.py`
 * exists on the server: the conversion had drifted between call sites once
 * already, and the version that drifts is always the one nobody is looking at.
 *
 * Stored loads keep the unit they were lifted in. These convert on read only.
 */

export type WeightUnit = 'kg' | 'lb'

/** Exact by definition: the international pound is 0.45359237 kg. */
export const POUNDS_TO_KG = 0.45359237

/** Anything that is not pounds is kilograms, including a missing unit. */
export function asUnit(value: string | null | undefined): WeightUnit {
  return (value ?? '').trim().toLowerCase().startsWith('lb') ? 'lb' : 'kg'
}

export function toKg(weight: number, unit: string | null | undefined): number {
  return asUnit(unit) === 'lb' ? weight * POUNDS_TO_KG : weight
}
