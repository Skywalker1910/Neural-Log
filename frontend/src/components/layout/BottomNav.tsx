import { useState } from 'react'
import { NavLink } from 'react-router'
import { Menu } from 'lucide-react'

import { cn } from '../../lib/cn'
import { accentText, OVERFLOW_SECTIONS, PRIMARY_SECTIONS, SETTINGS_SECTION } from '../../navigation'
import { Modal } from '../ui/Modal'

const TAB_CLASSES =
  'flex flex-1 flex-col items-center justify-center gap-1 py-2 text-caption transition-colors'

/**
 * Mobile navigation. Deliberately a thumb-reachable tab bar rather than a
 * shrunken sidebar - logging has to be fast from a phone (brief §42).
 */
export function BottomNav() {
  const [moreOpen, setMoreOpen] = useState(false)

  return (
    <>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface-card/95 backdrop-blur lg:hidden"
      >
        {PRIMARY_SECTIONS.map((section) => {
          const Icon = section.icon
          return (
            <NavLink
              key={section.path}
              to={section.path}
              end={section.path === '/'}
              className={({ isActive }) =>
                cn(TAB_CLASSES, isActive ? 'text-ink' : 'text-ink-subtle')
              }
            >
              {({ isActive }) => (
                <>
                  <Icon
                    size={20}
                    className={isActive ? accentText[section.accent] : undefined}
                    aria-hidden
                  />
                  <span>{section.label}</span>
                </>
              )}
            </NavLink>
          )
        })}

        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          className={cn(TAB_CLASSES, 'text-ink-subtle')}
        >
          <Menu size={20} aria-hidden />
          <span>More</span>
        </button>
      </nav>

      <Modal open={moreOpen} onClose={() => setMoreOpen(false)} title="All sections" size="sm">
        <ul className="grid grid-cols-2 gap-2">
          {[...OVERFLOW_SECTIONS, SETTINGS_SECTION].map((section) => {
            const Icon = section.icon
            return (
              <li key={section.path}>
                <NavLink
                  to={section.path}
                  onClick={() => setMoreOpen(false)}
                  className="flex items-center gap-2.5 rounded-md border border-line px-3 py-2.5 text-label text-ink-muted transition-colors hover:bg-surface-raised hover:text-ink"
                >
                  <Icon size={17} className={accentText[section.accent]} aria-hidden />
                  {section.label}
                </NavLink>
              </li>
            )
          })}
        </ul>
      </Modal>
    </>
  )
}
