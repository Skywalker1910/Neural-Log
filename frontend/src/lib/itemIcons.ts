/**
 * The checklist icon vocabulary, kept apart from the component that draws it.
 *
 * Two reasons. Fast Refresh only works on modules that export components and
 * nothing else, so a constant living beside `<ItemIcon>` would cost a full
 * reload on every edit. And the server keys below belong to the data, not to
 * one way of rendering it.
 */

/**
 * Keys the server can send. This is app.py's ICON_KEYS exactly - anything else
 * it stores has already been normalised to 'default' before it reaches us.
 */
export type ServerIconKey =
  | 'sun'
  | 'coffee'
  | 'workout'
  | 'code'
  | 'chess'
  | 'breakfast'
  | 'lunch'
  | 'water'
  | 'sleep'
  | 'default'

/**
 * Keys only the UI knows about. The server has no field for "this is a planning
 * question", and adding one would mean a migration plus rewriting the stored
 * paths of every existing account - their items are persisted per user, so a
 * change to the stock definitions would reach new accounts only.
 */
export type UiIconKey =
  | 'task'
  | 'journal'
  | 'plan'
  | 'rating'
  | 'reading'
  | 'mind'
  | 'steps'
  | 'people'
  | 'admin'
  | 'user'

export type ItemIconKey = ServerIconKey | UiIconKey

const SERVER_KEYS: ServerIconKey[] = [
  'sun', 'coffee', 'workout', 'code', 'chess',
  'breakfast', 'lunch', 'water', 'sleep', 'default',
]

/**
 * When the server says 'default' it means "no opinion", not "draw a placeholder".
 * Half the stock checklist carries it - most important task, journalling,
 * planning tomorrow, rate your day - and rendering all of them identically
 * produces a column of the same glyph repeated, which is worse than no icon.
 *
 * So infer one from the question text. First match wins, and anything that
 * matches nothing keeps the neutral default, which is the honest answer.
 */
const NAME_HINTS: [RegExp, ItemIconKey][] = [
  [/\brate\b|\brating\b|score your/i, 'rating'],
  [/journal|reflect|gratitude/i, 'journal'],
  [/\bplan\b|planning|tomorrow/i, 'plan'],
  [/important task|priority|deep work|\bfocus\b/i, 'task'],
  [/read|book|chapter/i, 'reading'],
  [/meditat|breath|mindful|stress/i, 'mind'],
  [/\bsteps\b|\bwalk|\bruns?\b|cardio/i, 'steps'],
  [/\bcall\b|family|friend|social/i, 'people'],
  [/water|hydrat/i, 'water'],
  [/sleep|bed|wake/i, 'sleep'],
  [/train|workout|gym|lift|exercise/i, 'workout'],
  [/study|learn|course/i, 'code'],
  [/meal|\beat\b|food|nutrition|diet/i, 'breakfast'],
]

function isServerKey(icon: string): icon is ServerIconKey {
  return (SERVER_KEYS as string[]).includes(icon)
}

/**
 * Pick the glyph for a checklist item.
 *
 * An explicit server icon always wins - if someone chose "chess" for their item,
 * that is their choice and no heuristic should override it. The name is only
 * consulted when the server had nothing to say.
 */
export function iconForItem(icon: string | undefined, name = ''): ItemIconKey {
  if (icon && isServerKey(icon) && icon !== 'default') return icon

  for (const [pattern, key] of NAME_HINTS) {
    if (pattern.test(name)) return key
  }
  return 'default'
}
