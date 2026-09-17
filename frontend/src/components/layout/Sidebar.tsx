import { NavLink } from 'react-router'
import { Activity, LogOut, PanelLeft, PanelLeftClose } from 'lucide-react'
import { m } from 'motion/react'

import { api } from '../../api/client'
import { cn } from '../../lib/cn'
import { accentText, NAV_SECTIONS, SETTINGS_SECTION, type NavSection } from '../../navigation'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

function SidebarLink({ section, collapsed }: { section: NavSection; collapsed: boolean }) {
  const Icon = section.icon

  return (
    <NavLink
      to={section.path}
      end={section.path === '/'}
      title={collapsed ? section.label : undefined}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-3 rounded-md px-3 py-2 text-label',
          'transition-colors duration-200 ease-apple',
          isActive ? 'text-ink' : 'text-ink-muted hover:text-ink',
          collapsed && 'justify-center px-0',
        )
      }
    >
      {({ isActive }) => (
        <>
          {/*
            The selected pill is one shared element that slides between items
            rather than a background that blinks on and off. layoutId is what
            makes it travel; it is the single most Apple-feeling detail in the
            whole shell, and it costs four lines.
          */}
          {isActive && (
            <m.span
              layoutId="sidebar-active"
              className="absolute inset-0 rounded-md bg-surface-card"
              transition={{ type: 'spring', stiffness: 380, damping: 34 }}
              aria-hidden
            />
          )}
          <Icon
            size={18}
            strokeWidth={1.9}
            className={cn(
              'relative shrink-0 transition-colors duration-200',
              isActive ? accentText[section.accent] : 'text-current',
            )}
            aria-hidden
          />
          {!collapsed && <span className="relative truncate">{section.label}</span>}
        </>
      )}
    </NavLink>
  )
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  return (
    <aside
      className={cn(
        // Sticky and full height, so the nav stays put while a long dashboard
        // scrolls past it - and the frosted material has something moving
        // underneath it to be a material *of*.
        'sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-line lg:flex',
        'material-chrome transition-[width] duration-300 ease-apple',
        collapsed ? 'w-[72px]' : 'w-60',
      )}
    >
      <div className={cn('flex h-16 items-center gap-2.5 px-4', collapsed && 'justify-center px-0')}>
        {/* App mark: a lucide glyph in a tinted rounded square, the same idiom
            as an app icon on a home screen. */}
        <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-brand text-white">
          <Activity size={18} strokeWidth={2.4} aria-hidden />
        </span>
        {!collapsed && (
          <span className="truncate text-section font-semibold tracking-tight text-ink">
            Neural Log
          </span>
        )}
      </div>

      <nav aria-label="Main" className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
        {NAV_SECTIONS.map((section) => (
          <SidebarLink key={section.path} section={section} collapsed={collapsed} />
        ))}
      </nav>

      <div className="space-y-0.5 border-t border-line px-3 py-3">
        <SidebarLink section={SETTINGS_SECTION} collapsed={collapsed} />
        {/*
          A button, not a link. Signing out changes state, and a GET that changes
          state is a link any other site can follow on your behalf - so /logout
          only acts on POST now. Going through the api client is what attaches
          the CSRF header.
        */}
        <button
          type="button"
          onClick={() => {
            void api
              .post('/logout')
              // Whatever the server said, the session is either gone or was
              // never valid; either way the right place to be is the sign-in
              // page. A full navigation rather than a route change, so every
              // cached query dies with the page.
              .finally(() => {
                window.location.href = '/login'
              })
          }}
          title={collapsed ? 'Sign out' : undefined}
          className={cn(
            'flex w-full items-center gap-3 rounded-md px-3 py-2 text-label text-ink-muted',
            'transition-colors duration-200 ease-apple hover:bg-surface-card hover:text-ink',
            collapsed && 'justify-center px-0',
          )}
        >
          <LogOut size={18} strokeWidth={1.9} className="shrink-0" aria-hidden />
          {!collapsed && <span>Sign out</span>}
        </button>
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={cn(
            'flex w-full items-center gap-3 rounded-md px-3 py-2 text-label text-ink-subtle',
            'transition-colors duration-200 ease-apple hover:bg-surface-card hover:text-ink',
            collapsed && 'justify-center px-0',
          )}
        >
          {collapsed ? (
            <PanelLeft size={18} strokeWidth={1.9} aria-hidden />
          ) : (
            <>
              <PanelLeftClose size={18} strokeWidth={1.9} aria-hidden />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}
