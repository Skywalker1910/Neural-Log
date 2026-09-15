import { useCallback, useSyncExternalStore } from 'react'

/**
 * Layout is Tailwind's job almost everywhere. This exists for the cases where a
 * component has to change its *data* rather than its styling at a breakpoint -
 * chart labels being the motivating example, since SVG text cannot wrap or
 * ellipsis its way out of a narrow card.
 *
 * useSyncExternalStore rather than useState + useEffect: matchMedia is an
 * external store, and subscribing to it that way avoids the extra render (and
 * the set-state-in-effect lint error) that the naive version produces.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const media = window.matchMedia(query)
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    },
    [query],
  )

  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false, // No matchMedia outside the browser; assume the wide layout.
  )
}
