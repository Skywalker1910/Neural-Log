import { useState } from 'react'
import { ArrowLeft, ChefHat, Plus } from 'lucide-react'
import { Link } from 'react-router'

import { useRecipes } from '../api/queries'
import type { Recipe } from '../api/types'
import { PageHeader } from '../components/layout/PageHeader'
import { RecipeBuilder } from '../components/nutrition/RecipeBuilder'
import { Button } from '../components/ui/Button'
import { PersonalBook, type BookPage } from '../components/ui/PersonalBook'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { SkeletonGrid } from '../components/ui/Skeleton'

export function RecipeBook() {
  const recipes = useRecipes()
  const [editing, setEditing] = useState<Recipe | null | undefined>(undefined)
  return <>
    <PageHeader title="Recipe book" description="The dishes you make your own. Ingredients, little rituals, and the method worth remembering."
      icon={ChefHat} accent="lifestyle" actions={<div className="flex items-center gap-4"><Link to="/nutrition" className="flex items-center gap-2 text-meta text-ink-muted"><ArrowLeft size={16} /> Nutrition</Link><Button icon={Plus} onClick={() => setEditing(null)}>Add recipe</Button></div>} />
    <QueryBoundary query={recipes} loading={<SkeletonGrid />}>{(data) => {
      const pages: BookPage[] = data.recipes.flatMap((recipe) => [
        { id: `recipe-${recipe.id}`, title: recipe.name, chapter: 'From your kitchen', content: <>
          <p className="mb-5 font-serif text-lg italic">{recipe.servings} serving{recipe.servings === 1 ? '' : 's'}{recipe.total_grams ? ` · ${recipe.total_grams} g cooked` : ''}</p>
          <h3 className="mb-4 text-xs font-bold uppercase tracking-widest">Ingredients</h3>
          <ul className="book-list">{recipe.ingredients.map((item) => <li key={item.position}><span className="min-w-16">{item.grams} g</span><span>{item.name}</span></li>)}</ul>
          {recipe.food && <p className="book-note">Per 100 g · {Math.round(recipe.food.kcal_per_100g)} kcal · {Math.round(recipe.food.protein_per_100g)} g protein</p>}
          <button type="button" className="book-link" onClick={() => setEditing(recipe)}>Edit this recipe</button>
        </> },
        { id: `method-${recipe.id}`, title: 'In the making', chapter: recipe.name, content: <>
          {recipe.instructions.length ? <ol className="book-list">{recipe.instructions.map((step, index) => <li key={index}><span>{String(index + 1).padStart(2, '0')}</span><span>{step}</span></li>)}</ol> : <p>Add the method to make this recipe your own.</p>}
          {recipe.notes && <p className="book-note">{recipe.notes}</p>}
          <button type="button" className="book-link mt-5" onClick={() => setEditing(recipe)}>Edit method</button>
        </> },
      ])
      return <PersonalBook title="Made in my kitchen" subtitle="Favourite flavours, familiar rituals, and recipes to return to." kind="recipe" pages={pages} />
    }}</QueryBoundary>
    {editing !== undefined && <RecipeBuilder key={editing?.id ?? 'new'} open recipe={editing} onClose={() => setEditing(undefined)} />}
  </>
}
