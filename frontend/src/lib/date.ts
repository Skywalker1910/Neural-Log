/**
 * Local calendar dates.
 *
 * Every "what day is it" in this app has to be the user's LOCAL date, never
 * UTC. `new Date().toISOString().slice(0, 10)` is the obvious thing to write and
 * it is wrong: west of UTC it rolls over to tomorrow in the evening, east of it
 * it stays on yesterday in the morning. Either way the app asks the server for a
 * day the user is not living in, and their log looks empty.
 *
 * That bug shipped in R3 and R4 - Nutrition, Lifestyle and Training each had
 * their own copy - and was caught only because a verification screenshot taken
 * at 20:02 in UTC-5 showed an empty day that the API definitely had data for.
 * One helper, used everywhere, so there is nowhere left for it to come back.
 *
 * Timestamps are a different question: an instant in time is correctly stored as
 * UTC, and `finished_at: new Date().toISOString()` stays as it is.
 */

/** A Date's local calendar date, as YYYY-MM-DD. */
export function isoDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** Today, where the user is. */
export function todayISO(): string {
  return isoDate(new Date())
}

/**
 * Move an ISO date by whole days.
 *
 * Built from local date parts rather than by adding milliseconds, so the days
 * either side of a daylight-saving change are still one day apart.
 */
export function shiftISO(iso: string, days: number): string {
  const [year, month, day] = iso.split('-').map(Number)
  return isoDate(new Date(year, month - 1, day + days))
}

/** "09/14" - compact axis and column labels. */
export function shortDate(iso: string): string {
  const [, month, day] = iso.split('-')
  return `${month}/${day}`
}
