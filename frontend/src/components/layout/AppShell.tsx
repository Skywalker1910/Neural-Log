import { useEffect, useState } from 'react'
import { Outlet } from 'react-router'

import { BottomNav } from './BottomNav'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

const COLLAPSE_KEY = 'neurallog:sidebar-collapsed'

export function AppShell() {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === 'true',
  )

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, String(collapsed))
  }, [collapsed])

  return (
    <div className="flex min-h-dvh bg-surface-base">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface-overlay focus:px-4 focus:py-2 focus:text-label focus:text-ink"
      >
        Skip to content
      </a>

      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        {/* Bottom padding clears the mobile tab bar. */}
        <main id="main" className="flex-1 px-4 pb-24 pt-6 lg:px-6 lg:pb-10">
          <Outlet />
        </main>
      </div>

      <BottomNav />
    </div>
  )
}
