import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router'

import { AppShell } from './components/layout/AppShell'
import { SkeletonGrid } from './components/ui/Skeleton'
import { Home } from './pages/Home'
import { NotFound } from './pages/NotFound'
import { Today } from './pages/Today'
import { Learning } from './pages/Learning'
import { Lifestyle } from './pages/Lifestyle'
import { Nutrition } from './pages/Nutrition'
import { Training } from './pages/Training'
import { WorkoutSession } from './pages/WorkoutSession'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { DESIGN_SECTION, NAV_SECTIONS, SETTINGS_SECTION } from './navigation'

/** Sections that have a real page now. Anything else still gets a placeholder. */
const BUILT = new Set(['/today', '/training', '/nutrition', '/lifestyle', '/learning'])

// Dev-facing gallery - no reason for it to ride along in the main bundle.
const DesignSystem = lazy(() =>
  import('./pages/DesignSystem').then((module) => ({ default: module.DesignSystem })),
)

/**
 * Phase 1 routes every section to an honest placeholder. Each later phase swaps
 * one of these for the real workspace; the shell around them doesn't change.
 */
export default function App() {
  const [, ...rest] = NAV_SECTIONS

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Home />} />
        <Route path="/today" element={<Today />} />
        <Route path="/training" element={<Training />} />
        <Route path="/training/:workoutId" element={<WorkoutSession />} />
        <Route path="/nutrition" element={<Nutrition />} />
        <Route path="/lifestyle" element={<Lifestyle />} />
        <Route path="/learning" element={<Learning />} />
        {rest
          .filter((section) => !BUILT.has(section.path))
          .map((section) => (
            <Route
              key={section.path}
              path={section.path}
              element={<PlaceholderPage section={section} />}
            />
          ))}
        <Route
          path={SETTINGS_SECTION.path}
          element={<PlaceholderPage section={SETTINGS_SECTION} />}
        />
        <Route
          path={DESIGN_SECTION.path}
          element={
            <Suspense fallback={<SkeletonGrid />}>
              <DesignSystem />
            </Suspense>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
