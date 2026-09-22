import { useState } from 'react'
import { ChefHat } from 'lucide-react'

import { useRecipes } from '../api/queries'
import { PageHeader } from '../components/layout/PageHeader'
import { PersonalBook } from '../components/ui/PersonalBook'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { SkeletonGrid } from '../components/ui/Skeleton'

export function RecipeBook() {
  const recipes = useRecipes()
  const [selected, setSelected] = useState<number | null>(null)
  return <>
    <PageHeader title="Recipe book" description="Your own dishes, ingredients, and method in one place." icon={ChefHat} accent="lifestyle" />
    <QueryBoundary query={recipes} loading={<SkeletonGrid />}>{(data) => {
      const recipe = data.recipes.find((item) => item.id === selected) ?? data.recipes[0]
      if (!recipe) return <p className="rounded-lg border border-line bg-surface-card p-6 text-label text-ink-muted">Build a dish in Nutrition and it will appear here as its own recipe card.</p>
      return <div className="grid gap-4 lg:grid-cols-[13rem_1fr]"><aside className="flex gap-2 overflow-x-auto lg:flex-col">{data.recipes.map((item) => <button key={item.id} type="button" onClick={() => setSelected(item.id)} className={`shrink-0 rounded-lg border px-3 py-2 text-left text-meta ${item.id === recipe.id ? 'border-lifestyle bg-lifestyle/15 text-ink' : 'border-line text-ink-muted'}`}>{item.name}</button>)}</aside>
        <PersonalBook title={recipe.name} subtitle={`${recipe.servings} serving${recipe.servings === 1 ? '' : 's'} · personal recipe`} accent="lifestyle" pages={[
          { title: 'Ingredients', content: <ul className="space-y-2">{recipe.ingredients.map((item) => <li key={`${item.food_id}-${item.position}`} className="flex justify-between border-b border-line pb-2"><span>{item.name}</span><span className="tabular text-ink-muted">{item.grams} g</span></li>)}</ul> },
          { title: 'Method', content: recipe.instructions.length ? <ol className="space-y-3">{recipe.instructions.map((step, index) => <li key={index} className="flex gap-3"><span className="tabular text-lifestyle">{index + 1}</span><span>{step}</span></li>)}</ol> : <p className="text-ink-muted">No method yet. Edit this dish in Nutrition to add one.</p> },
          { title: 'Serving notes', content: <div className="space-y-3"><p>{recipe.notes || 'No serving notes yet.'}</p><p className="text-meta text-ink-muted">{recipe.food ? `${Math.round(recipe.food.kcal_per_100g)} kcal per 100g` : 'Macros are calculated from ingredients.'}</p></div> },
        ]} />
      </div>
    }}</QueryBoundary>
  </>
}
