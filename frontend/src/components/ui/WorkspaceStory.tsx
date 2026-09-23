import { LifeIllustration, type IllustrationKind } from './LifeIllustration'

const STORIES = {
  training: { eyebrow: 'Make room for movement', title: 'Your next chapter is a stronger one.', description: 'Build a routine you enjoy. Every session has a place in your story.' },
  nutrition: { eyebrow: 'Made for your everyday', title: 'Good food. Your way.', description: 'Keep the meals you love, discover your rhythm, and collect recipes worth making again.' },
  lifestyle: { eyebrow: 'A little space for yourself', title: 'Rest. Reflect. Begin again.', description: 'A good night, a quiet walk, a thought worth keeping. The little things belong here too.' },
} satisfies Record<Exclude<IllustrationKind, 'journey'>, { eyebrow: string; title: string; description: string }>

export function WorkspaceStory({ kind }: { kind: keyof typeof STORIES }) {
  const story = STORIES[kind]
  return <section className={`workspace-story story-${kind}`} aria-label={story.eyebrow}>
    <div><p className="story-eyebrow">{story.eyebrow}</p><h2>{story.title}</h2><p>{story.description}</p></div>
    <LifeIllustration kind={kind} />
  </section>
}
