import { useMemo, useState } from 'react'
import { m } from 'motion/react'
import {
  ChefHat, ChevronLeft, ChevronRight, Flame, Info, Plus, ScanLine, Trash2,
  UtensilsCrossed,
} from 'lucide-react'

import type { Food, FoodEntry, Meal, NutritionDay, Recipe, Targets } from '../api/types'
import {
  useAssistantState, useCreateFood, useDeleteFoodEntry, useDeleteRecipe,
  useLogFood, useNutritionDay, useRecipes,
} from '../api/queries'
import { FoodPicker } from '../components/nutrition/FoodPicker'
import { RecipeBuilder } from '../components/nutrition/RecipeBuilder'
import { LabelScanner } from '../components/nutrition/LabelScanner'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { Modal } from '../components/ui/Modal'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { cn } from '../lib/cn'
import { amountLabel } from '../lib/foodUnits'
import { shiftISO, todayISO } from '../lib/date'
import { spring } from '../lib/motion'

const MEALS: Meal[] = ['breakfast', 'lunch', 'dinner', 'snack']

/**
 * A macro against its target.
 *
 * Overshooting is drawn differently from filling up, because for calories the
 * two are not the same thing - a bar that simply caps at 100% would show a
 * 4,000 kcal day on a 2,000 target as "done".
 */
function MacroBar({
  label, value, target, unit = 'g', accent = 'bg-lifestyle', estimated,
}: {
  label: string
  value: number
  target: number | null
  unit?: string
  accent?: string
  estimated?: boolean
}) {
  const pct = target ? Math.min(100, (value / target) * 100) : 0
  const over = target ? value > target * 1.05 : false

  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-meta text-ink-muted">{label}</span>
        <span className="tabular text-meta text-ink">
          {Math.round(value)}
          {target != null && (
            <span className="text-ink-subtle">
              {' / '}{Math.round(target)}{unit}
              {estimated && <span title="Estimated from your profile">*</span>}
            </span>
          )}
          {target == null && <span className="text-ink-subtle">{unit}</span>}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-raised">
        <m.div
          className={cn('h-full rounded-full', over ? 'bg-warning' : accent)}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={spring.soft}
        />
      </div>
    </div>
  )
}

function CustomFoodForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateFood()
  const [form, setForm] = useState({
    name: '', kcal_per_100g: '', protein_per_100g: '',
    carbs_per_100g: '', fat_per_100g: '', fibre_per_100g: '',
  })

  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }))

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!form.name.trim() || form.kcal_per_100g === '') return
    create.mutate(
      {
        name: form.name.trim(),
        kcal_per_100g: Number(form.kcal_per_100g),
        protein_per_100g: Number(form.protein_per_100g) || 0,
        carbs_per_100g: Number(form.carbs_per_100g) || 0,
        fat_per_100g: Number(form.fat_per_100g) || 0,
        fibre_per_100g: Number(form.fibre_per_100g) || 0,
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Custom food"
      description="For something the library does not carry. Values are per 100g — that is how packaging states them, and it is what lets a dish be built from it."
    >
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Name</span>
          <input
            value={form.name} required autoFocus onChange={set('name')}
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
          />
        </label>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {([
            ['kcal_per_100g', 'Calories'],
            ['protein_per_100g', 'Protein (g)'],
            ['carbs_per_100g', 'Carbs (g)'],
            ['fat_per_100g', 'Fat (g)'],
            ['fibre_per_100g', 'Fibre (g)'],
          ] as const).map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-meta text-ink-muted">{label}</span>
              <input
                type="number" min="0" step="0.1" inputMode="decimal"
                value={form[key]} onChange={set(key)}
                required={key === 'kcal_per_100g'}
                className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
              />
            </label>
          ))}
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={create.isPending}>Save</Button>
        </div>
      </form>
    </Modal>
  )
}

function MealSection({
  meal, entries, onAdd, onRemove,
}: {
  meal: Meal
  entries: FoodEntry[]
  onAdd: (meal: Meal) => void
  onRemove: (id: number) => void
}) {
  const calories = entries.reduce((total, entry) => total + entry.macros.calories, 0)

  return (
    <Card
      title={<span className="capitalize">{meal}</span>}
      subtitle={entries.length ? `${Math.round(calories)} kcal` : 'Nothing logged'}
      icon={UtensilsCrossed}
      accent="lifestyle"
      action={
        <Button size="sm" variant="ghost" icon={Plus} onClick={() => onAdd(meal)}
                aria-label={`Add to ${meal}`} />
      }
    >
      {entries.length === 0 ? (
        <p className="text-label text-ink-subtle">Nothing yet.</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {entries.map((entry) => (
            <m.div
              key={entry.id}
              layout
              transition={spring.snappy}
              className="flex items-center gap-3 rounded-md border border-line bg-surface-base px-3 py-2"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-label text-ink">{entry.name}</span>
                <span className="block truncate text-meta text-ink-subtle">
                  {amountLabel(Math.round(entry.grams), entry)} · P {Math.round(entry.macros.protein_g)}g
                  {' · '}C {Math.round(entry.macros.carbs_g)}g
                  {' · '}F {Math.round(entry.macros.fat_g)}g
                </span>
              </span>
              <span className="tabular shrink-0 text-label text-ink">
                {Math.round(entry.macros.calories)}
              </span>
              <button
                type="button"
                onClick={() => onRemove(entry.id)}
                aria-label={`Remove ${entry.name}`}
                className="shrink-0 text-ink-subtle transition-colors hover:text-danger"
              >
                <Trash2 size={14} />
              </button>
            </m.div>
          ))}
        </div>
      )}
    </Card>
  )
}

function EnergyBalance({ totals, targets }: { totals: NutritionDay['totals']; targets: Targets }) {
  if (targets.estimated_tdee == null) {
    return (
      <p className="text-label text-ink-subtle">
        Set your height, year of birth and activity level in Profile, and log a body
        weight, and this becomes an energy balance. Until then there is nothing
        honest to compare against.
      </p>
    )
  }

  const balance = Math.round(totals.calories - targets.estimated_tdee)
  const direction = balance > 0 ? 'surplus' : 'deficit'

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline gap-2">
        <span className={cn('tabular text-metric',
          balance > 0 ? 'text-warning' : 'text-success')}>
          {balance > 0 ? '+' : ''}{balance}
        </span>
        <span className="text-label text-ink-muted">kcal {direction}</span>
      </div>
      <p className="flex items-start gap-1.5 text-meta text-ink-subtle">
        <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
        Against an estimated {targets.estimated_tdee} kcal maintenance
        (BMR {targets.estimated_bmr}, {targets.goal}). Mifflin-St Jeor carries
        roughly 10% error, and activity multipliers more — treat it as a starting
        point to adjust from, not a measurement.
      </p>
    </div>
  )
}

export function Nutrition() {
  const assistant = useAssistantState()
  const [scanning, setScanning] = useState(false)
  const [date, setDate] = useState(todayISO)
  const query = useNutritionDay(date)
  const recipes = useRecipes()
  const logFood = useLogFood(date)
  const removeEntry = useDeleteFoodEntry(date)
  const removeRecipe = useDeleteRecipe()

  const [picking, setPicking] = useState<Meal | null>(null)
  const [customOpen, setCustomOpen] = useState(false)
  /** undefined = closed, null = new dish, a recipe = editing it. */
  const [editingRecipe, setEditingRecipe] = useState<Recipe | null | undefined>(undefined)

  const isToday = date === todayISO()

  const remaining = useMemo(() => {
    const target = query.data?.targets.calories
    if (!target) return null
    return Math.round(target - (query.data?.totals.calories ?? 0))
  }, [query.data])

  function handlePick(food: Food, grams: number, meal: Meal) {
    logFood.mutate({ food_id: food.id, grams, meal }, { onSuccess: () => setPicking(null) })
  }

  return (
    <>
      <PageHeader
        title="Nutrition"
        description="Hitting the targets you set feeds Discipline. What you weigh is context, not a score."
        icon={UtensilsCrossed}
        accent="lifestyle"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {/* Hidden when the instance has no assistant, like everything else
                that needs a model. The catalogue and the recipe builder work
                exactly as before without it. */}
            {assistant.data?.configured && (
              <Button size="sm" variant="secondary" icon={ScanLine}
                      onClick={() => setScanning(true)}>
                Scan a label
              </Button>
            )}
            <Button size="sm" icon={ChefHat} onClick={() => setEditingRecipe(null)}>
              Build a dish
            </Button>
            <Button size="sm" variant="primary" icon={Plus} onClick={() => setPicking('snack')}>
              Add food
            </Button>
          </div>
        }
      />

      <div className="mb-4 flex items-center gap-2">
        <Button size="sm" variant="ghost" icon={ChevronLeft}
                aria-label="Previous day" onClick={() => setDate(shiftISO(date, -1))} />
        <span className="tabular text-label text-ink">
          {isToday ? 'Today' : date}
        </span>
        <Button size="sm" variant="ghost" icon={ChevronRight}
                aria-label="Next day" disabled={isToday}
                onClick={() => setDate(shiftISO(date, 1))} />
      </div>

      <LabelScanner open={scanning} onClose={() => setScanning(false)} />

      <QueryBoundary query={query} loading={<SkeletonGrid />}>
        {(day) => (
          <RevealGroup className="flex flex-col gap-4">
            <Reveal>
              <Card title="Today's totals" icon={Flame} accent="lifestyle">
                <div className="flex flex-col gap-4">
                  <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
                    <div>
                      <p className="tabular text-metric text-ink">
                        {Math.round(day.totals.calories)}
                      </p>
                      <p className="text-label text-ink-muted">calories</p>
                    </div>
                    {remaining != null && (
                      <div>
                        <p className={cn('tabular text-section',
                          remaining < 0 ? 'text-warning' : 'text-ink')}>
                          {remaining < 0 ? `${Math.abs(remaining)} over` : remaining}
                        </p>
                        <p className="text-label text-ink-muted">
                          {remaining < 0 ? 'target' : 'remaining'}
                        </p>
                      </div>
                    )}
                    {day.targets.sources.calories === 'estimated' && (
                      <Badge tone="info">target estimated</Badge>
                    )}
                    {day.targets.sources.calories === 'unknown' && (
                      <Badge tone="neutral">no target set</Badge>
                    )}
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <MacroBar
                      label="Protein" value={day.totals.protein_g}
                      target={day.targets.protein_g} accent="bg-fitness"
                      estimated={day.targets.sources.protein === 'estimated'}
                    />
                    <MacroBar
                      label="Carbs" value={day.totals.carbs_g}
                      target={day.targets.carbs_g} accent="bg-discipline"
                      estimated={day.targets.sources.carbs === 'estimated'}
                    />
                    <MacroBar
                      label="Fat" value={day.totals.fat_g}
                      target={day.targets.fat_g} accent="bg-goals"
                      estimated={day.targets.sources.fat === 'estimated'}
                    />
                    <MacroBar
                      label="Fibre" value={day.totals.fibre_g}
                      target={day.targets.fibre_g} accent="bg-lifestyle"
                    />
                  </div>

                  {Object.values(day.targets.sources).includes('estimated') && (
                    <p className="text-caption text-ink-subtle">
                      * estimated from your profile rather than set by you
                    </p>
                  )}
                </div>
              </Card>
            </Reveal>

            <Reveal className="grid gap-4 lg:grid-cols-2">
              {MEALS.map((meal) => (
                <MealSection
                  key={meal}
                  meal={meal}
                  entries={day.by_meal[meal] ?? []}
                  onAdd={setPicking}
                  onRemove={(id) => removeEntry.mutate(id)}
                />
              ))}
            </Reveal>

            <Reveal>
              <Card title="Energy balance" icon={Flame} accent="recovery">
                <EnergyBalance totals={day.totals} targets={day.targets} />
              </Card>
            </Reveal>

            <Reveal>
              <Card
                title="Your dishes"
                subtitle="Cooked meals you can log in one tap"
                icon={ChefHat}
                accent="lifestyle"
                action={
                  <Button size="sm" variant="ghost" icon={Plus}
                          onClick={() => setEditingRecipe(null)}>
                    New
                  </Button>
                }
              >
                {(recipes.data?.recipes.length ?? 0) === 0 ? (
                  <EmptyState
                    icon={ChefHat}
                    title="No dishes yet"
                    description="Describe something you cook, pick the ingredients that went in, and it becomes one entry in the food picker."
                    action={
                      <Button variant="primary" icon={Plus}
                              onClick={() => setEditingRecipe(null)}>
                        Build a dish
                      </Button>
                    }
                  />
                ) : (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {recipes.data?.recipes.map((recipe) => (
                      <div
                        key={recipe.id}
                        className="flex items-center gap-2 rounded-md border border-line bg-surface-base px-3 py-2"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-label text-ink">
                            {recipe.name}
                          </span>
                          <span className="block truncate text-meta text-ink-subtle">
                            {recipe.ingredients.length} ingredient
                            {recipe.ingredients.length === 1 ? '' : 's'}
                            {recipe.food &&
                              ` · ${Math.round(recipe.food.kcal_per_100g)} kcal/100g`}
                          </span>
                        </span>
                        <Button
                          size="sm" variant="ghost" icon={Trash2}
                          aria-label={`Delete ${recipe.name}`}
                          onClick={() => removeRecipe.mutate(recipe.id)}
                        />
                        <Button size="sm" variant="secondary"
                                onClick={() => setEditingRecipe(recipe)}>
                          Edit
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </Reveal>
          </RevealGroup>
        )}
      </QueryBoundary>

      {/*
        Mounted only while open, and keyed on the meal, for the same reason the
        recipe builder below is: FoodPicker seeds its own state from props, so a
        single long-lived instance kept whichever meal it was first opened with.
        Every food logged from Breakfast or Lunch was landing under Snack.
      */}
      {picking !== null && (
      <FoodPicker
        key={picking}
        open
        meal={picking}
        onClose={() => setPicking(null)}
        onPick={handlePick}
        busy={logFood.isPending}
        onCreateFood={() => { setPicking(null); setCustomOpen(true) }}
        onCreateRecipe={() => { setPicking(null); setEditingRecipe(null) }}
      />
      )}

      <CustomFoodForm open={customOpen} onClose={() => setCustomOpen(false)} />

      {/* Keyed and conditionally mounted so the builder seeds from whichever
          dish you opened - a single long-lived instance would keep the first
          dish's ingredients when you opened the second. */}
      {editingRecipe !== undefined && (
        <RecipeBuilder
          key={editingRecipe?.id ?? 'new'}
          open
          recipe={editingRecipe}
          onClose={() => setEditingRecipe(undefined)}
        />
      )}
    </>
  )
}
