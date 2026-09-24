import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router'
import { AnimatePresence, m } from 'motion/react'

import { AssistantLauncher } from '../assistant/AssistantPanel'
import { LevelUpCelebration } from '../gamification/LevelUpCelebration'
import { pageTransition, reducedVariants } from '../../lib/motion'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { BottomNav } from './BottomNav'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

const COLLAPSE_KEY = 'neurallog:sidebar-collapsed'

export function AppShell() {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === 'true',
  )
  const location = useLocation()
  const reduced = usePrefersReducedMotion()

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, String(collapsed))
  }, [collapsed])

  return (
    <div className="flex min-h-dvh bg-surface-base" data-page-theme={location.pathname.split('/')[1] || 'home'}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface-overlay focus:px-4 focus:py-2 focus:text-label focus:text-ink"
      >
        Skip to content
      </a>

      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        {/* Bottom padding clears the mobile tab bar. Max width so a dashboard
            doesn't stretch across an ultrawide monitor. */}
        <main id="main" className="mx-auto w-full max-w-[1600px] flex-1 px-4 pb-24 pt-8 lg:px-8 lg:pb-14">
          {/*
            mode="wait" so the outgoing page finishes before the next arrives -
            crossfading two dashboards produces a flash of overlapping numbers.
            Keyed on pathname, so only real navigations animate.
          */}
          <AnimatePresence mode="wait" initial={false}>
            <m.div
              key={location.pathname}
              variants={reduced ? reducedVariants : pageTransition}
              initial="hidden"
              animate="visible"
              exit="exit"
            >
              <Outlet />
            </m.div>
          </AnimatePresence>
        </main>
      </div>

      <BottomNav />

      {/* In the shell rather than on a page: a level-up is caused by XP, and
          since R7 every workspace awards it. */}
      <LevelUpCelebration />

      {/* Also shell-level, for the opposite reason: the point of the assistant
          is to log something without leaving the page you were reading. It
          renders nothing at all when the instance has no API key. */}
      <AssistantLauncher />
    </div>
  )
}
