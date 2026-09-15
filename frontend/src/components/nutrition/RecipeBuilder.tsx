import { useMemo, useState } from 'react'
import { m } from 'motion/react'
import { Info, Plus, Trash2 } from 'lucide-react'

import type { Food, Recipe, RecipeIngredient } from '../../api/types'
import { useSaveRecipe } from '../../api/queries'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { FoodPicker } from './FoodPicker'
import { spring } from '../../lib/motion'

interface RecipeBuilderProps {
  open: boolean
  onClose: () => void
  /** Null builds a new dish; a recipe edits it in place. */
  recipe: Recipe | null
}

/**
 * Describe a cooked dish once, then log it like any other food.
 *
 * The macros are always computed from the ingredients rather than typed, so
 * correcting an ingredient corrects every meal already logged with the dish.
 */
export function RecipeBuilder({ open, onClose, recipe }: RecipeBuilderProps) {
  const save = useSaveRecipe()

  const [name, setName] = useState(recipe?.name ?? '')
  const [servings, setServings] = useState(String(recipe?.servings ?? 1))
  const [cookedGrams, setCookedGrams] = useState(
    recipe?.total_grams != null ? String(recipe.total_grams) : '',
  )
  const [ingredients, setIngredients] = useState<RecipeIngredient[]>(
    recipe?.ingredients ?? [],
  )
  const [picking, setPicking] = useState(false)

  const rawGrams = ingredients.reduce((total, item) => total + (item.grams || 0), 0)

  const totals = useMemo(() => {
    const sum = { calories: 0, protein: 0, carbs: 0, fat: 0, fibre: 0 }
    for (const item of ingredients) {
      const factor = (item.grams || 0) / 100
      sum.calories += (item.kcal_per_100g ?? 0) * factor
      sum.protein += (item.protein_per_100g ?? 0) * factor
      sum.carbs += (item.carbs_per_100g ?? 0) * factor
      sum.fat += (item.fat_per_100g ?? 0) * factor
      sum.fibre += (item.fibre_per_100g ?? 0) * factor
    }
    return sum
  }, [ingredients])

  const basis = Number(cookedGrams) > 0 ? Number(cookedGrams) : rawGrams
  const perServing = Number(servings) > 0 ? Number(servings) : 1

  function add(food: Food, grams: number) {
    setIngredients((current) => [...current, {
      food_id: food.id,
      grams,
      name: food.name,
      category: food.category,
      kcal_per_100g: food.kcal_per_100g,
      protein_per_100g: food.protein_per_100g,
      carbs_per_100g: food.carbs_per_100g,
      fat_per_100g: food.fat_per_100g,
      fibre_per_100g: food.fibre_per_100g,
    }])
    setPicking(false)
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim() || ingredients.length === 0) return
    save.mutate(
      {
        id: recipe?.id,
        name: name.trim(),
        servings: perServing,
        total_grams: Number(cookedGrams) > 0 ? Number(cookedGrams) : null,
        ingredients: ingredients.map((item, position) => ({
          food_id: item.food_id, grams: item.grams, position,
        })),
      },
      { onSuccess: onClose },
    )
  }

  return (
    <>
      <Modal
        open={open && !picking}
        onClose={onClose}
        title={recipe ? 'Edit dish' : 'Build a dish'}
        description="Add what went into the pan. The macros are worked out from the ingredients, so fixing one later fixes every meal you logged with this."
        size="lg"
      >
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-meta text-ink-muted">What is it?</span>
              <input
                value={name} required autoFocus
                onChange={(event) => setName(event.target.value)}
                placeholder="Chicken curry"
                className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-meta text-ink-muted">Servings</span>
              <input
                type="number" min="1" step="0.5" value={servings}
                onChange={(event) => setServings(event.target.value)}
                className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
              />
            </label>
          </div>

          <div className="flex flex-col gap-2">
            {ingredients.length === 0 && (
              <p className="py-2 text-label text-ink-subtle">
                No ingredients yet.
              </p>
            )}

            {ingredients.map((item, index) => (
              <m.div
                key={`${item.food_id}-${index}`}
                layout
                transition={spring.snappy}
                className="grid grid-cols-[1fr_5rem_1.5rem] items-center gap-2"
              >
                <span className="truncate text-label text-ink">{item.name}</span>
                <input
                  type="number" min="1" inputMode="decimal" value={item.grams}
                  onChange={(event) => setIngredients((current) => current.map(
                    (entry, i) => (i === index
                      ? { ...entry, grams: Number(event.target.value) }
                      : entry),
                  ))}
                  aria-label={`Grams of ${item.name}`}
                  className="rounded-md border border-line bg-surface-base px-2 py-1.5 text-right text-label tabular text-ink outline-none focus:border-brand"
                />
                <button
                  type="button"
                  onClick={() => setIngredients((current) =>
                    current.filter((_, i) => i !== index))}
                  aria-label={`Remove ${item.name}`}
                  className="text-ink-subtle transition-colors hover:text-danger"
                >
                  <Trash2 size={14} />
                </button>
              </m.div>
            ))}

            <Button
              type="button" size="sm" variant="ghost" icon={Plus}
              onClick={() => setPicking(true)} className="self-start"
            >
              Add ingredient
            </Button>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-meta text-ink-muted">
              Cooked weight (grams) — optional
            </span>
            <input
              type="number" min="1" inputMode="decimal" value={cookedGrams}
              onChange={(event) => setCookedGrams(event.target.value)}
              placeholder={rawGrams ? `${Math.round(rawGrams)} raw` : 'weigh the pan'}
              className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
            />
            <span className="flex items-start gap-1.5 text-caption text-ink-subtle">
              <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
              Rice absorbs water, roasting drives it off. Weighing the finished
              dish is what makes a portion of it accurate — leave it blank and the
              raw total is used instead.
            </span>
          </label>

          {ingredients.length > 0 && (
            <div className="rounded-md border border-line bg-surface-base p-3">
              <p className="mb-2 text-meta text-ink-muted">
                Per serving ({Math.round(basis / perServing)}g of {Math.round(basis)}g)
              </p>
              <div className="grid grid-cols-4 gap-2">
                {[
                  ['kcal', Math.round(totals.calories / perServing)],
                  ['protein', `${Math.round(totals.protein / perServing)}g`],
                  ['carbs', `${Math.round(totals.carbs / perServing)}g`],
                  ['fat', `${Math.round(totals.fat / perServing)}g`],
                ].map(([label, value]) => (
                  <div key={label}>
                    <p className="tabular text-section text-ink">{value}</p>
                    <p className="text-caption text-ink-subtle">{label}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button
              type="submit" variant="primary" loading={save.isPending}
              disabled={ingredients.length === 0}
            >
              {recipe ? 'Save dish' : 'Create dish'}
            </Button>
          </div>
        </form>
      </Modal>

      <FoodPicker
        open={picking}
        onClose={() => setPicking(false)}
        onPick={add}
      />
    </>
  )
}
