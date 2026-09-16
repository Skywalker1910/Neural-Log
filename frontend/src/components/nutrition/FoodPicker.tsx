import { useMemo, useState } from 'react'

import { ChefHat, Minus, Plus, Search, UtensilsCrossed } from 'lucide-react'

import type { Food, FoodCategory, Meal } from '../../api/types'
import { useFoods } from '../../api/queries'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { EmptyState } from '../ui/EmptyState'
import { Modal } from '../ui/Modal'
import { QueryBoundary } from '../ui/QueryBoundary'
import { SkeletonGrid } from '../ui/Skeleton'
import { cn } from '../../lib/cn'
import {
  amountLabel, fromGrams, measureSummary, measuresFor, toGrams,
  type MeasureKey,
} from '../../lib/foodUnits'

const CATEGORIES: { value: '' | FoodCategory; label: string }[] = [
  { value: '', label: 'All' },
  { value: 'protein', label: 'Protein' },
  { value: 'grain', label: 'Grains' },
  { value: 'legume', label: 'Legumes' },
  { value: 'vegetable', label: 'Veg' },
  { value: 'fruit', label: 'Fruit' },
  { value: 'dairy', label: 'Dairy' },
  { value: 'nut-seed', label: 'Nuts' },
  { value: 'fat', label: 'Fats' },
  { value: 'beverage', label: 'Drinks' },
  { value: 'prepared', label: 'Dishes' },
  { value: 'sweet', label: 'Sweets' },
  { value: 'condiment', label: 'Condiments' },
]

const MEALS: Meal[] = ['breakfast', 'lunch', 'dinner', 'snack']

interface FoodPickerProps {
  open: boolean
  onClose: () => void
  onPick: (food: Food, grams: number, meal: Meal) => void
  /** Which meal the picker defaults to. */
  meal?: Meal
  busy?: boolean
  onCreateFood?: () => void
  onCreateRecipe?: () => void
}

/**
 * Pick a food, then say how much.
 *
 * The portion step is a second screen rather than a column in the list because
 * it is where the actual thinking happens - "one medium banana" versus "120g" -
 * and squeezing a quantity field into every row would make the list unusable on
 * a phone.
 */
export function FoodPicker({
  open, onClose, onPick, meal = 'snack', busy, onCreateFood, onCreateRecipe,
}: FoodPickerProps) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<'' | FoodCategory>('')
  const [selected, setSelected] = useState<Food | null>(null)
  const [amount, setAmount] = useState('100')
  const [measureKey, setMeasureKey] = useState<MeasureKey>('g')
  const [chosenMeal, setChosenMeal] = useState<Meal>(meal)

  // Which units this particular food can be entered in. Cups appear only where
  // the cup weight is known, pieces only for things you count.
  const measures = useMemo(() => measuresFor(selected), [selected])
  const measure = measures.find((option) => option.key === measureKey) ?? measures[0]
  const grams = String(toGrams(Number(amount) || 0, measure))

  const query = useFoods({ q: search, category })

  const preview = useMemo(() => {
    if (!selected) return null
    const factor = (Number(grams) || 0) / 100
    return {
      calories: Math.round(selected.kcal_per_100g * factor),
      protein: Math.round(selected.protein_per_100g * factor),
      carbs: Math.round(selected.carbs_per_100g * factor),
      fat: Math.round(selected.fat_per_100g * factor),
    }
  }, [selected, grams])

  function reset() {
    setSelected(null)
    setAmount('100')
    setMeasureKey('g')
    setSearch('')
  }

  /**
   * Opening a food picks the unit it is most naturally measured in: a piece for
   * eggs, a serving for a dish you cooked, otherwise grams or millilitres.
   */
  function choose(food: Food) {
    const options = measuresFor(food)
    const best = options[0]
    setSelected(food)
    setMeasureKey(best.key)
    setAmount(String(best.key === 'g' || best.key === 'ml' ? 100 : best.step))
  }

  function switchMeasure(next: MeasureKey) {
    const from = measures.find((option) => option.key === measureKey)
    const to = measures.find((option) => option.key === next)
    // Carry the quantity across rather than resetting it - switching from grams
    // to cups should show how many cups that was, not throw the number away.
    setAmount(String(fromGrams(toGrams(Number(amount) || 0, from), to)))
    setMeasureKey(next)
  }

  function confirm() {
    // Whatever unit it was entered in, the server is told grams.
    const inGrams = Number(grams)
    if (!selected || !inGrams || inGrams <= 0) return
    onPick(selected, inGrams, chosenMeal)
    reset()
  }

  if (selected) {
    return (
      <Modal
        open={open}
        onClose={() => { reset(); onClose() }}
        title={selected.name}
        description={`${Math.round(selected.kcal_per_100g)} kcal per 100g`}
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-1.5">
            {MEALS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setChosenMeal(option)}
                className={cn(
                  'rounded-full border px-3 py-1 text-meta capitalize transition-colors',
                  chosenMeal === option
                    ? 'border-lifestyle bg-lifestyle/15 text-lifestyle'
                    : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
                )}
              >
                {option}
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-meta text-ink-muted">How much?</span>

            {measures.length > 1 && (
              <div className="flex flex-wrap gap-1.5">
                {measures.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    onClick={() => switchMeasure(option.key)}
                    className={cn(
                      'rounded-pill border px-3 py-1 text-meta capitalize transition-colors duration-200 ease-apple',
                      option.key === measure?.key
                        ? 'border-lifestyle bg-lifestyle/15 text-lifestyle'
                        : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}

            {/*
              Counted things get a counter. Typing 100 into a grams box to mean
              two eggs is arithmetic the app should be doing, and the same is
              true of a dish cooked into four portions that you ate one of.
            */}
            {measure && (measure.key === 'piece' || measure.key === 'serving') ? (
              <div className="flex items-center gap-3">
                <Button
                  size="sm" variant="secondary" icon={Minus}
                  aria-label={`One fewer ${measure.label}`}
                  disabled={Number(amount) <= 1}
                  onClick={() => setAmount(String(Math.max(1, (Number(amount) || 1) - 1)))}
                />
                <span className="tabular min-w-16 text-center text-metric text-ink">
                  {Number(amount) || 1}
                </span>
                <Button
                  size="sm" variant="secondary" icon={Plus}
                  aria-label={`One more ${measure.label}`}
                  onClick={() => setAmount(String((Number(amount) || 0) + 1))}
                />
                <span className="text-label text-ink-muted">
                  {measure.label}
                  {Number(amount) === 1 ? '' : 's'}
                </span>
              </div>
            ) : (
              <input
                type="number" min="0" step={measure?.step ?? 1} inputMode="decimal"
                value={amount} autoFocus
                aria-label={`Amount in ${measure?.label ?? 'grams'}`}
                onChange={(event) => setAmount(event.target.value)}
                className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
              />
            )}

            {/* What it came to, so a cup or a count is never a mystery. */}
            <p className="text-meta text-ink-subtle">
              {measureSummary(Number(amount) || 0, measure) ?? amountLabel(grams, selected)}
            </p>
          </div>

          {preview && (
            <div className="grid grid-cols-4 gap-2 rounded-md border border-line bg-surface-base p-3">
              {[
                ['kcal', preview.calories],
                ['protein', `${preview.protein}g`],
                ['carbs', `${preview.carbs}g`],
                ['fat', `${preview.fat}g`],
              ].map(([label, value]) => (
                <div key={label}>
                  <p className="tabular text-section text-ink">{value}</p>
                  <p className="text-caption text-ink-subtle">{label}</p>
                </div>
              ))}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setSelected(null)}>Back</Button>
            <Button variant="primary" onClick={confirm} loading={busy}>Add</Button>
          </div>
        </div>
      </Modal>
    )
  }

  return (
    <Modal
      open={open}
      onClose={() => { reset(); onClose() }}
      title="Add food"
      size="lg"
    >
      <div className="mb-4 flex flex-col gap-3">
        <label className="relative block">
          <Search
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle"
            aria-hidden
          />
          <input
            type="search" value={search} autoFocus
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search foods and recipes"
            aria-label="Search foods"
            className="w-full rounded-md border border-line bg-surface-base py-2 pl-9 pr-3 text-label text-ink outline-none transition-colors focus:border-brand"
          />
        </label>

        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map((option) => (
            <button
              key={option.value || 'all'}
              type="button"
              onClick={() => setCategory(option.value)}
              className={cn(
                'rounded-full border px-3 py-1 text-meta transition-colors',
                category === option.value
                  ? 'border-lifestyle bg-lifestyle/15 text-lifestyle'
                  : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>

        {(onCreateFood || onCreateRecipe) && (
          <div className="flex flex-wrap gap-2">
            {onCreateRecipe && (
              <Button size="sm" variant="secondary" icon={ChefHat} onClick={onCreateRecipe}>
                Build a dish
              </Button>
            )}
            {onCreateFood && (
              <Button size="sm" variant="ghost" icon={Plus} onClick={onCreateFood}>
                Custom food
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="max-h-[50vh] overflow-y-auto">
        <QueryBoundary
          query={query}
          loading={<SkeletonGrid />}
          isEmpty={(data) => data.foods.length === 0}
          empty={
            <EmptyState
              icon={UtensilsCrossed}
              title="Nothing matches that"
              description="Try another category, or build it as a custom food or a dish."
            />
          }
        >
          {(data) => (
            <div className="flex flex-col gap-1.5">
              {data.foods.map((food) => (
                <button
                  key={food.id}
                  type="button"
                  onClick={() => choose(food)}
                  className="flex items-center gap-3 rounded-md border border-line bg-surface-card px-3 py-2 text-left transition-colors hover:border-line-strong hover:bg-surface-raised"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-label text-ink">{food.name}</span>
                    <span className="block truncate text-meta text-ink-subtle">
                      {Math.round(food.kcal_per_100g)} kcal
                      {' · '}P {Math.round(food.protein_per_100g)}g
                      {' · '}C {Math.round(food.carbs_per_100g)}g
                      {' · '}F {Math.round(food.fat_per_100g)}g
                      <span className="text-ink-subtle"> per 100g</span>
                    </span>
                  </span>
                  {food.source === 'recipe' && <Badge tone="info">dish</Badge>}
                  {food.source === 'custom' && <Badge tone="neutral">custom</Badge>}
                </button>
              ))}
            </div>
          )}
        </QueryBoundary>
      </div>
    </Modal>
  )
}
