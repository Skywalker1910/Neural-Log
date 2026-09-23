import { LibraryBig } from 'lucide-react'

import { PageHeader } from '../components/layout/PageHeader'
import { BookPreview } from '../components/ui/BookPreview'

export function Library() {
  return <>
    <PageHeader title="Your library" description="Movement, meals, and moments. Three books, one growing collection." icon={LibraryBig} accent="goals" />
    <section className="collection-room" aria-label="Personal books">
      <div className="collection-heading"><span>The Neural Log collection</span><h2>A little more you,<br />with every page.</h2><p>Pull a book off the shelf. Everything you save in Training, Nutrition, and Lifestyle lives here too.</p></div>
      <div className="collection-shelf"><BookPreview kind="exercise" /><BookPreview kind="recipe" /><BookPreview kind="journal" /></div>
      <p className="collection-footnote">The same books, wherever you open them. Not separate copies.</p>
    </section>
  </>
}
