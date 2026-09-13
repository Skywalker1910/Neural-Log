/** Join conditional class names. Deliberately tiny - no need for clsx here. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}
