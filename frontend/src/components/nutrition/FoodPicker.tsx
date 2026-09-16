import { useMemo, useState } from 'react'

import { ChefHat, Plus, Search, UtensilsCrossed } from 'lucide-react'

import type { Food, FoodCategory, Meal } from '../../api/types'
import { useFoods } from '../../api/queries'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { EmptyState } from '../ui/EmptyState'
import { Modal } from '../ui/Modal'
import { QueryBoundary } from '../ui/QueryBoundary'
import { SkeletonGrid } from '../ui/Skeleton'
import { cn } from '../../lib/cn'
import { amountLabel, unitOf } from '../../lib/foodUnits'

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
  const [grams, setGrams] = useState('100')
  const [chosenMeal, setChosenMeal] = useState<Meal>(meal)

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
    setGrams('100')
    setSearch('')
  }

  function confirm() {
    const amount = Number(grams)
    if (!selected || !amount || amount <= 0) return
    onPick(selected, amount, chosenMeal)
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

          <label className="flex flex-col gap-1">
            <span className="text-meta text-ink-muted">
              Amount ({unitOf(selected) === 'ml' ? 'millilitres' : 'grams'})
            </span>
            <input
              type="number" min="1" inputMode="decimal" value={grams} autoFocus
              onChange={(event) => setGrams(event.target.value)}
              className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
            />
          </label>

          {selected.serving_grams && (
            <Button
              size="sm" variant="secondary"
              onClick={() => setGrams(String(selected.serving_grams))}
              className="self-start"
            >
              {selected.serving_name ?? 'One serving'} ({amountLabel(selected.serving_grams, selected)})
            </Button>
          )}

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
                  onClick={() => setSelected(food)}
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
