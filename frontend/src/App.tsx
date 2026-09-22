import { lazy, Suspense, type ComponentType } from 'react'
import { Route, Routes } from 'react-router'

import { AppShell } from './components/layout/AppShell'
import { SkeletonGrid } from './components/ui/Skeleton'
import { Home } from './pages/Home'
import { NotFound } from './pages/NotFound'
import { Today } from './pages/Today'
import { DESIGN_SECTION, SETTINGS_SECTION } from './navigation'

/*
  Route-level code splitting (R10).

  Every page lived in one chunk, which had grown to 589kB minified - so opening
  the app downloaded the recipe builder, the goal editor and the onboarding flow
  before it could render Home.

  Home and Today stay eager. They are the daily loop, they are what a bookmark
  and the mobile tab bar point at, and splitting them would trade a smaller
  download for a spinner on the screen people open every evening. Everything else
  is a place you go deliberately, where one chunk fetch is unnoticeable next to
  the navigation itself.
*/
function page<T extends Record<string, ComponentType<object>>>(
  loader: () => Promise<T>,
  name: keyof T,
) {
  return lazy(() => loader().then((module) => ({ default: module[name] })))
}

const Training = page(() => import('./pages/Training'), 'Training')
const ExerciseLibrary = page(() => import('./pages/ExerciseLibrary'), 'ExerciseLibrary')
const WorkoutSession = page(() => import('./pages/WorkoutSession'), 'WorkoutSession')
const Nutrition = page(() => import('./pages/Nutrition'), 'Nutrition')
const Feed = page(() => import('./pages/Feed'), 'Feed')
const RecipeBook = page(() => import('./pages/RecipeBook'), 'RecipeBook')
const ExerciseBook = page(() => import('./pages/ExerciseBook'), 'ExerciseBook')
const JournalBook = page(() => import('./pages/JournalBook'), 'JournalBook')
const Lifestyle = page(() => import('./pages/Lifestyle'), 'Lifestyle')
const Learning = page(() => import('./pages/Learning'), 'Learning')
const Goals = page(() => import('./pages/Goals'), 'Goals')
const Achievements = page(() => import('./pages/Achievements'), 'Achievements')
const Analytics = page(() => import('./pages/Analytics'), 'Analytics')
const Profile = page(() => import('./pages/Profile'), 'Profile')
const Settings = page(() => import('./pages/Settings'), 'Settings')
const Welcome = page(() => import('./pages/Welcome'), 'Welcome')
const DesignSystem = page(() => import('./pages/DesignSystem'), 'DesignSystem')
const Admin = page(() => import('./pages/Admin'), 'Admin')

/**
 * One Suspense boundary around the whole outlet rather than one per route.
 *
 * Per-route boundaries would be identical copies of the same fallback, and the
 * boundary has to sit inside AppShell either way so the chrome stays put while a
 * page chunk arrives - a spinner that replaces the sidebar reads as a page load,
 * not a navigation.
 */
function Lazy({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<SkeletonGrid />}>{children}</Suspense>
}

export default function App() {
  return (
    <Routes>
      {/* Outside AppShell on purpose: the first-run flow is a full-screen task,
          and framing it with the sidebar of an app you have not set up yet is
          both noisy and an invitation to wander off mid-question. */}
      <Route path="/welcome" element={<Lazy><Welcome /></Lazy>} />

      <Route element={<AppShell />}>
        <Route index element={<Home />} />
        <Route path="/today" element={<Today />} />
        <Route path="/training" element={<Lazy><Training /></Lazy>} />
        {/* Before the :workoutId route so "library" is not read as a session id.
            React Router ranks static segments above dynamic ones anyway, but the
            order makes the intent obvious to the next person. */}
        <Route path="/training/library" element={<Lazy><ExerciseLibrary /></Lazy>} />
        <Route path="/training/:workoutId" element={<Lazy><WorkoutSession /></Lazy>} />
        <Route path="/nutrition" element={<Lazy><Nutrition /></Lazy>} />
        <Route path="/feed" element={<Lazy><Feed /></Lazy>} />
        <Route path="/recipes" element={<Lazy><RecipeBook /></Lazy>} />
        <Route path="/exercises" element={<Lazy><ExerciseBook /></Lazy>} />
        <Route path="/journal" element={<Lazy><JournalBook /></Lazy>} />
        <Route path="/lifestyle" element={<Lazy><Lifestyle /></Lazy>} />
        <Route path="/learning" element={<Lazy><Learning /></Lazy>} />
        <Route path="/goals" element={<Lazy><Goals /></Lazy>} />
        <Route path="/achievements" element={<Lazy><Achievements /></Lazy>} />
        <Route path="/analytics" element={<Lazy><Analytics /></Lazy>} />
        <Route path="/profile" element={<Lazy><Profile /></Lazy>} />
        <Route path={SETTINGS_SECTION.path} element={<Lazy><Settings /></Lazy>} />
        <Route path={DESIGN_SECTION.path} element={<Lazy><DesignSystem /></Lazy>} />
        <Route path="/admin" element={<Lazy><Admin /></Lazy>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
