import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import '@fontsource-variable/inter'
import './index.css'
import App from './App.tsx'

// Flask mounts the SPA under /app (see serve_spa in app.py).
const BASENAME = '/app'

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
      <BrowserRouter basename={BASENAME}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
