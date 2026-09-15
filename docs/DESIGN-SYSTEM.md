# Design System

## Motivation

Neural Log is growing from one checklist page into ten workspaces - Home, Today,
Training, Nutrition, Lifestyle, Learning, Goals, Achievements, Analytics, Profile.
Ten pages designed independently become ten different apps wearing the same logo.

So the visual decisions live here, once, as tokens and primitives. A workspace
should be assembled from these pieces rather than styled from scratch. If you find
yourself picking a hex value or a font size by hand while building a feature, that's
the signal something is missing from this document.

Everything below is defined in `frontend/src/index.css` under Tailwind v4's
`@theme`, which turns each token into a utility class (`--color-surface-card` ->
`bg-surface-card`).

## Surfaces

The app is dark by default. Depth comes from surface colour rather than shadow -
shadows on a near-black ground mostly read as mud.

| Token | Value | Used for |
|---|---|---|
| `surface-base` | `#0b0c0e` | Page background, sidebar |
| `surface-card` | `#131519` | Cards, panels, the default raised plane |
| `surface-raised` | `#1a1d22` | Hover states, inputs, skeletons, icon chips |
| `surface-overlay` | `#21252b` | Modals, tooltips, popovers |
| `line` | `#23272e` | Hairline borders |
| `line-strong` | `#323841` | Emphasised borders, scrollbar thumbs |

## Text

| Token | Value | Used for |
|---|---|---|
| `ink` | `#f2f4f7` | Primary text. Off-white, not pure white - less glare |
| `ink-muted` | `#9ba3af` | Labels, secondary text, axis ticks |
| `ink-subtle` | `#6b7280` | Metadata, captions, disabled |

## Colour

One accent carries interactive intent. Category colours carry *identity* - they
belong to sections and data series, never to ordinary buttons or links.

| Token | Value | Meaning |
|---|---|---|
| `brand` | `#e5484d` | Primary actions, focus rings, active nav |
| `fitness` | `#f76b15` | Training. Orange, so it stays distinct from `brand` |
| `learning` | `#5b7cfa` | Learning, knowledge, analytics |
| `lifestyle` | `#3dbe72` | Nutrition, lifestyle |
| `goals` | `#a96bf0` | Goals, milestones |
| `discipline` | `#e0a93b` | Discipline, streaks, XP, achievements |
| `recovery` | `#38bec9` | Sleep, recovery, hydration |
| `success` / `warning` / `danger` / `info` | - | Semantic status only |
| `artwork-disc` | `#dfe3e8` | Light disc behind the PNG artwork (see Icons) |

**Tailwind caveat:** class names are found by scanning source for literal strings,
so `text-${accent}` produces nothing. Accent classes are spelled out in the
`accentText` / `accentBg` / `accentStroke` maps in `frontend/src/navigation.ts` -
use those rather than building class names at runtime.

## Typography

Inter, self-hosted via `@fontsource-variable/inter` (not a CDN - one less
third-party dependency at page load, and it keeps the AWS deploy self-contained).

| Token | Size | Used for |
|---|---|---|
| `text-metric-xl` | 3.25rem | Hero figures - XP, daily score |
| `text-metric` | 2.25rem | Dashboard metric cards |
| `text-heading` | 1.75rem | Page titles |
| `text-section` | 1.125rem | Card and section headings |
| `text-label` | 0.8125rem | Body text, labels, table cells |
| `text-meta` | 0.75rem | Secondary metadata |
| `text-caption` | 0.6875rem | Uppercase column headers |

Numbers use the `.tabular` class (tabular figures) anywhere they update in place,
so digits don't jitter as values change.

## Components

Primitives live in `frontend/src/components/ui/`, charts in
`frontend/src/components/charts/`, shell pieces in `frontend/src/components/layout/`.

| Component | Purpose |
|---|---|
| `Card` | The surface every panel is built on; optional header with icon/action |
| `MetricCard` | One big scannable figure, with optional period-over-period delta |
| `StatCard` | Compact icon + label + value, for dense rows |
| `ProgressCard` | "Protein 142 / 165 g" with a bar |
| `ProgressRing` | Circular progress, 0-100 |
| `AttributeBadge` | One RPG attribute as a ring |
| `ArtworkBadge` | The custom PNG artwork, on its light disc |
| `Button` | primary / secondary / ghost / danger, with loading state |
| `Badge` | Small status pill |
| `EmptyState` | Never show a blank card - say what's missing and offer the action |
| `Skeleton`, `SkeletonCard`, `SkeletonGrid` | Loading placeholders |
| `Modal` | Escape to close, scroll lock, `aria-modal`, focus on panel |
| `ConfirmationDialog` | Modal preset for destructive actions |
| `DataTable` | Typed columns, responsive column hiding, row highlighting |
| `QueryBoundary` | Loading / error / empty / retry around any query |
| `AttributeRadar` | The attribute radar chart, with previous-period overlay |
| `TrendChart` | Single-series trend over time |

### QueryBoundary

Every data-backed section should render through it. It is how the "handle loading,
success, empty, error and retry" rule gets enforced structurally rather than
remembered per component:

```tsx
<QueryBoundary query={stats} isEmpty={(d) => d.total_days === 0} empty={<EmptyState .../>}>
  {(data) => <MetricCard label="Days logged" value={data.total_days} />}
</QueryBoundary>
```

### Charts

Recharts is roughly 300kB - more than the rest of the app put together. Import
charts from `components/charts` (the barrel), never from the implementation files
directly: the barrel wraps them in `React.lazy` + `Suspense` so Recharts loads as a
separate chunk only when a chart actually renders.

## Icons

Two deliberate sources, with a clear boundary:

- **Lucide** (`lucide-react`) for all UI chrome - navigation, buttons, metric
  labels, status. One consistent stroke style across the app.
- **The custom PNG artwork** (`static/images/icons/`, generated by
  `scripts/build_icons.py`) for achievements, attributes and badges - the places
  where personality motivates. Rendered through `ArtworkBadge`, which sits it on a
  light disc because the artwork is near-black line art drawn for a light ground and
  would otherwise disappear against the dark UI.

## Accessibility

- Focus is always visible - a `brand` outline via `:focus-visible`, never removed.
- `prefers-reduced-motion` is honoured globally in `index.css`, and separately by
  the charts (`usePrefersReducedMotion`, since chart libraries animate in JS).
- The shell provides a skip link, landmark elements, and `aria-label`s on the nav.
- Progress bars and rings expose `role="progressbar"` / `role="img"` with values.

## Responsive

Not a shrunken desktop. The sidebar is replaced below `lg` by a thumb-reachable
bottom tab bar (four primary sections plus an overflow sheet), because logging data
from a phone is the most common real-world use.

## Motion

Animation lives in `frontend/src/lib/motion.ts` for the same reason colour lives in
`index.css`: ten workspaces built by hand would each invent their own idea of "fast".

| Primitive | Use |
|---|---|
| `rise` / `slideIn` / `scaleIn` | Entrance variants - fade with a small translation |
| `stagger(step, delay)` | Container variant; children inherit the sequence |
| `pageTransition` | Route changes, deliberately plainer than component motion |
| `spring.snappy` / `spring.soft` | Interactive feedback vs. larger surfaces |
| `<Reveal>` / `<RevealGroup>` | What most pages actually use |
| `<AnimatedNumber>` | Counts a value up; drives a MotionValue, not React state |

Rules this encodes:

- **Motion is short.** Anything over ~400ms is in the way on a dashboard opened daily.
- **Entrances move a small distance.** Large translations read as decoration.
- **Springs for interaction, easing for state.** Overshoot feels physical under a
  cursor and wrong on a progress bar.
- **Nothing is load-bearing.** Under `prefers-reduced-motion` every variant collapses
  to a crossfade via `reducedVariants`, and the UI still makes sense. Content is never
  gated behind an animation that might not run.

### Why `m` and not `motion`

Components import `m.div`, never `motion.div`, and the root wraps the app in
`<LazyMotion features={loadDomAnimation} strict>`. The full motion build costs ~44kB
gzipped; this keeps the feature set in a chunk fetched after first paint. `strict`
makes an accidental `motion.*` import throw rather than quietly pulling the heavy
build back in.

Charts animate in JS rather than CSS, so they take `isAnimationActive` from
`usePrefersReducedMotion()` directly.
