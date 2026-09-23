import type { HTMLAttributes, PointerEvent } from 'react'

import { cn } from '../../lib/cn'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'

export function TiltSurface({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  const reduced = usePrefersReducedMotion()

  function reset(event: PointerEvent<HTMLDivElement>) {
    event.currentTarget.style.removeProperty('--tilt-x')
    event.currentTarget.style.removeProperty('--tilt-y')
    event.currentTarget.style.removeProperty('--light-x')
    event.currentTarget.style.removeProperty('--light-y')
  }

  function move(event: PointerEvent<HTMLDivElement>) {
    if (reduced || event.pointerType !== 'mouse') return
    const bounds = event.currentTarget.getBoundingClientRect()
    const horizontal = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width))
    const vertical = Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height))
    event.currentTarget.style.setProperty('--tilt-x', `${(0.5 - vertical) * 6}deg`)
    event.currentTarget.style.setProperty('--tilt-y', `${(horizontal - 0.5) * 6}deg`)
    event.currentTarget.style.setProperty('--light-x', `${horizontal * 100}%`)
    event.currentTarget.style.setProperty('--light-y', `${vertical * 100}%`)
  }

  return <div {...props} className={cn('tilt-surface', className)} onPointerMove={move}
    onPointerLeave={reset} onPointerCancel={reset}>
    {children}
  </div>
}
