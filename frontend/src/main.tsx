import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LazyMotion } from 'motion/react'

import '@fontsource-variable/inter'
import './index.css'
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
        LazyMotion + the `m` components instead of `motion`: the full motion
        bundle costs ~44kB gzipped, which is a lot for a dashboard opened daily.
        domAnimation covers everything used here (enter/exit, variants, springs)
        and is loaded as a separate chunk after first paint; `strict` makes an
        accidental `motion.*` import throw rather than quietly pulling the heavy
        build back in.
      */}
      <LazyMotion features={loadDomAnimation} strict>
        <BrowserRouter basename={BASENAME}>
          <App />
        </BrowserRouter>
      </LazyMotion>
    </QueryClientProvider>
  </StrictMode>,
)
