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

## The design language

R8 retuned the tokens to Apple's design language. That language is not a colour
scheme, and copying their blue would not have produced it. It is four habits:

1. **Contrast at the extremes.** A true black ground, near-white type, and
   neutral grey between them. The previous palette was a blue-tinted charcoal;
   the tint was the main thing separating it from the reference.
2. **Chrome is a material, not a panel.** The sidebar, top bar and mobile tab bar
   are translucent and blurred, with content visibly scrolling underneath.
3. **Type does the work.** Large, tight, heavy headlines and small quiet labels,
   with little in between and no decorative border where space will do.
4. **Motion is physical and brief.** One easing curve for the whole app.

What did **not** change: the category accents. Those are data identity, and
restraint applies to chrome, not to a radar chart that has to tell sleep from
strength at a glance.

## Surfaces

The app is dark by default. Depth comes from surface colour rather than shadow -
shadows on a near-black ground mostly read as mud.

| Token | Value | Used for |
|---|---|---|
| `surface-base` | `#000000` | Page background. True black, so an OLED panel switches those pixels off |
| `surface-card` | `#1d1d1f` | Cards, panels, the default raised plane |
| `surface-raised` | `#2c2c2e` | Hover states, inputs, skeletons, icon chips |
| `surface-overlay` | `#3a3a3c` | Modals, tooltips, popovers |
| `line` | `#2a2a2c` | Hairline borders |
| `line-strong` | `#48484a` | Emphasised borders, scrollbar thumbs |

### Materials

Two utility classes in `index.css` rather than tokens, because they are a
recipe rather than a value:

| Class | Used for |
|---|---|
| `material-chrome` | Sidebar, top bar, mobile tab bar |
| `material-panel` | Sheets and popovers that float over content |

Both are `saturate(180%) blur(...)` over a translucent ground. The `saturate()` is
the part that matters and the part everyone omits: it lets colour bleed through,
which is why Apple's bars look alive rather than like sheets of grey glass. Both
have an opaque fallback under `@supports`, because without `backdrop-filter` the
content would scroll illegibly underneath.

## Text

| Token | Value | Used for |
|---|---|---|
| `ink` | `#f5f5f7` | Primary text. Off-white, not pure white - less glare |
| `ink-muted` | `#a1a1a6` | Labels, secondary text, axis ticks |
| `ink-subtle` | `#6e6e73` | Metadata, captions, disabled |

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

**Tailwind caveat:** class names are found by scanning source for literal strings,
so `text-${accent}` produces nothing. Accent classes are spelled out in the
`accentText` / `accentBg` / `accentStroke` maps in `frontend/src/navigation.ts` -
use those rather than building class names at runtime.

## Typography

The stack leads with the SF faces, so the app renders in Apple's own type on Apple
hardware. Everywhere else it falls back to Inter, self-hosted via
`@fontsource-variable/inter` (not a CDN - one less third-party dependency at page
load, and it keeps the AWS deploy self-contained). Inter shares SF's proportions
closely enough that the layout does not shift between them.

The scale is deliberately bimodal - headlines are big, tight and heavy, labels are
small and quiet, and almost nothing lives in the middle. Tracking goes *negative*
as size goes up; at display sizes, default letter spacing reads as loose.

| Token | Size | Tracking | Used for |
|---|---|---|---|
| `text-display` | 3.5rem | -0.03em | Hero headline |
| `text-metric-xl` | 3rem | -0.025em | Hero figures - XP, daily score |
| `text-metric` | 2.125rem | -0.022em | Dashboard metric cards |
| `text-heading` | 1.75rem | -0.02em | Page titles |
| `text-section` | 1.0625rem | -0.01em | Card and section headings |
| `text-label` | 0.8125rem | -0.005em | Body text, labels, table cells |
| `text-meta` | 0.75rem | - | Secondary metadata |
| `text-caption` | 0.6875rem | +0.06em | Uppercase column headers |

## Radii

| Token | Value | Used for |
|---|---|---|
| `radius-sm` | 8px | Inputs, small chips |
| `radius-md` | 12px | Icon tiles, list rows, inner panels |
| `radius-lg` | 18px | Cards |
| `radius-xl` | 24px | Modals, large panels |
| `radius-pill` | 980px | Buttons, badges, progress bars |

Buttons are full pills. That single decision does more to make the app read as
Apple-like than any colour, and it is why `Button` no longer takes `rounded-md`.

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
| `ItemIcon` | Checklist / attribute glyph in a tinted tile, accent-coloured |
| `Button` | primary / secondary / ghost / danger, with loading state |
| `Badge` | Small status pill |
| `EmptyState` | Never show a blank card - say what's missing and offer the action |
| `Skeleton`, `SkeletonCard`, `SkeletonGrid` | Loading placeholders |
| `Modal` | Escape to close, scroll lock, `aria-modal`, focus on panel |
| `ConfirmationDialog` | Modal preset for destructive actions |
| `DataTable` | Typed columns, responsive column hiding, row highlighting |
| `QueryBoundary` | Loading / error / empty / retry around any query |
| `AttributeRadar` | The attribute radar chart, with previous-period overlay |
| `CalendarHeatmap` | Adherence grid, one square per day. Plain CSS, not Recharts |
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

**One source: Lucide** (`lucide-react`), everywhere - navigation, buttons, metric
labels, status, checklist items, achievements.

### Why the custom artwork was removed

The hand-drawn PNG set was near-black line art produced for a light ground. On a
black UI every one of them needed a pale disc behind it to be visible at all,
which meant a checklist rendered as a column of white circles punched through the
page. The disc was not a style choice; it was a workaround for art that did not
belong on this background.

It also could not take an accent colour, could not scale past its raster size, and
cost a request each. A line icon from the same family as the rest of the chrome
inherits `currentColor`, stays sharp at any size, and ships in a bundle already
loaded.

`scripts/build_icons.py` and `static/images/icons/` are left in place - the classic
dashboard at `/classic` still uses them.

### `ItemIcon` and inferred glyphs

Checklist items carry an icon key from the server's `ICON_KEYS`, a closed set of
ten. Most stock items carry `'default'`, which means *no opinion* rather than
*draw a placeholder* - and rendering all of them identically produced four
consecutive copies of the same glyph.

So `iconForItem(icon, name)` in `lib/itemIcons.ts` infers one from the question
text when the server has nothing to say ("plan tomorrow's tasks" -> clipboard,
"rate your day" -> star). An explicit server icon always wins: if someone chose
"chess" for their item, no heuristic should override it.

This lives in the UI rather than the database because paths are stored **per
user** - changing the stock definitions would reach new accounts only, and fixing
existing ones would mean a migration that rewrites people's own checklists.

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
| `EASE` / `ease-apple` | The one easing curve, shared by motion variants and CSS |
| `<Reveal>` / `<RevealGroup>` | What most pages actually use |
| `<AnimatedNumber>` | Counts a value up; drives a MotionValue, not React state |

One curve, `cubic-bezier(0.28, 0.11, 0.32, 1)`, exported as `EASE` from
`motion.ts` and as `--ease-apple` from `index.css` so a CSS transition and a motion
variant on the same element cannot disagree. It leaves immediately and settles
slowly, which is what makes these interfaces feel unhurried at durations this short.

The selected item in the sidebar is a single element that *travels* between rows
(`layoutId`), rather than a background that blinks on and off. It is four lines and
it is the most Apple-feeling detail in the shell.

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

## Layout traps worth knowing

**`min-width: auto`.** A grid or flex item refuses to shrink below its content by
default. A `Card` holding a `DataTable` therefore widened past the viewport and
scrolled the whole page sideways - the table's own `overflow-x-auto` never got a
chance to engage. This has now been the cause four separate times, so `min-w-0` is
baked into both `Card` and `Reveal` rather than remembered per call site.

`Reveal` needed it separately: it sits *between* a `Card` and the grid, so it is
the element that actually inherits `min-width: auto`, and `Card`'s own floor does
nothing from behind it.

`PageHeader`'s action slot is the related case. `shrink-0` is right - a pair of
buttons should not be squeezed to fit a long title - but alone it also lets the
actions grow past the viewport, and a `flex-wrap` inside them never fires because
the container is never the thing under pressure. It carries `max-w-full` too.

Any *other* row that is a grid item and holds fixed-width controls needs the same
floor; the Training routine rows are the current example.

**Probing for it.** Compare `document.documentElement.scrollWidth` against
`clientWidth` at 390px. Equal means no horizontal scroll. `scripts/shoot.mjs`
takes a `SHOOT_EVAL` env var for exactly this.
