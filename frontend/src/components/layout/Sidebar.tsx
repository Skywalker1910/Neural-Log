import { NavLink } from 'react-router'
import { LogOut, PanelLeft, PanelLeftClose } from 'lucide-react'

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
          'group relative flex items-center gap-3 rounded-md px-3 py-2 text-label transition-colors',
          isActive ? 'bg-surface-raised text-ink' : 'text-ink-muted hover:bg-surface-card hover:text-ink',
          collapsed && 'justify-center px-0',
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span
              className="absolute left-0 h-5 w-0.5 rounded-r-full bg-current"
              aria-hidden
            />
          )}
          <Icon
            size={18}
            className={cn('shrink-0', isActive ? accentText[section.accent] : 'text-current')}
            aria-hidden
          />
          {!collapsed && <span className="truncate">{section.label}</span>}
        </>
      )}
    </NavLink>
  )
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  return (
    <aside
      className={cn(
        'hidden shrink-0 flex-col border-r border-line bg-surface-base lg:flex',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      <div className={cn('flex h-16 items-center gap-2.5 px-4', collapsed && 'justify-center px-0')}>
        <img
          src="/static/images/app-logo.png"
          alt=""
          width={28}
          height={28}
          className="shrink-0 object-contain"
        />
        {!collapsed && (
          <span className="truncate text-label font-semibold uppercase tracking-widest text-ink">
            Neural Log
          </span>
        )}
      </div>

      <nav aria-label="Main" className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
        {NAV_SECTIONS.map((section) => (
          <SidebarLink key={section.path} section={section} collapsed={collapsed} />
        ))}
      </nav>

      <div className="space-y-0.5 border-t border-line px-2 py-2">
        <SidebarLink section={SETTINGS_SECTION} collapsed={collapsed} />
        <a
          href="/logout"
          title={collapsed ? 'Sign out' : undefined}
          className={cn(
            'flex items-center gap-3 rounded-md px-3 py-2 text-label text-ink-muted transition-colors hover:bg-surface-card hover:text-ink',
            collapsed && 'justify-center px-0',
          )}
        >
          <LogOut size={18} className="shrink-0" aria-hidden />
          {!collapsed && <span>Sign out</span>}
        </a>
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={cn(
            'flex w-full items-center gap-3 rounded-md px-3 py-2 text-label text-ink-subtle transition-colors hover:bg-surface-card hover:text-ink',
            collapsed && 'justify-center px-0',
          )}
        >
          {collapsed ? (
            <PanelLeft size={18} aria-hidden />
          ) : (
            <>
              <PanelLeftClose size={18} aria-hidden />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}
