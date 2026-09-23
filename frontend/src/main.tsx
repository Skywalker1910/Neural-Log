import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LazyMotion } from 'motion/react'

import '@fontsource-variable/inter'
import './index.css'
import './engagement.css'
import { loadDomAnimation } from './lib/motionFeatures'
import App from './App.tsx'

// Flask serves the SPA at the site root (see index() in app.py).
const BASENAME = '/'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Personal tracking data changes when *you* change it, so aggressive
      // refetching buys nothing. Retry once for transient network blips.
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {/*
        LazyMotion + the `m` components instead of `motion`. `m` is a stub that
        carries no features of its own, so the feature set is registered once
        here rather than pulled in at every call site, and `strict` makes an
        accidental `motion.*` import throw rather than quietly pulling the full
        build back in. domAnimation covers everything used here - enter/exit,
        variants, springs.

        What this does NOT do, despite how it reads: defer the features past
        first paint. `motion/react` is statically imported by ~20 components, so
        the dynamic import in motionFeatures.ts cannot be split out - rolldown
        said so out loud (INEFFECTIVE_DYNAMIC_IMPORT) until R10's route splitting
        moved those importers into lazy chunks, and even now the features land in
        the eagerly-preloaded vendor chunk beside React rather than in one of
        their own. Deferring them properly would mean importing `m` from
        `motion/react-m` everywhere, which is a real option if the initial
        payload ever needs the ~30kB back.
      */}
      <LazyMotion features={loadDomAnimation} strict>
        <BrowserRouter basename={BASENAME}>
          <App />
        </BrowserRouter>
      </LazyMotion>
    </QueryClientProvider>
  </StrictMode>,
)
