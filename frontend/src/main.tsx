import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode, type ComponentType } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import { Layout } from './App'
import { Muted } from './components/ui'
import './index.css'
import { CurrencyProvider } from './lib/currency'
import { ThemeProvider } from './lib/theme'

// Pages are split so each chart library (recharts, lightweight-charts) loads only where used.
const page = (load: () => Promise<{ Component: ComponentType }>) => ({ lazy: load })
const dashboard = page(() => import('./pages/Dashboard').then((m) => ({ Component: m.Dashboard })))
const transactions = page(() =>
  import('./pages/Transactions').then((m) => ({ Component: m.Transactions })),
)
const importPage = page(() => import('./pages/Import').then((m) => ({ Component: m.Import })))
const projection = page(() =>
  import('./pages/Projection').then((m) => ({ Component: m.Projection })),
)
const assetDetail = page(() =>
  import('./pages/AssetDetail').then((m) => ({ Component: m.AssetDetail })),
)
const compare = page(() => import('./pages/Compare').then((m) => ({ Component: m.Compare })))
const rules = page(() => import('./pages/Rules').then((m) => ({ Component: m.Rules })))

const queryClient = new QueryClient({
  defaultOptions: {
    // Backend caches quotes for 60s; refetching more often gains nothing.
    queries: { staleTime: 60_000, refetchOnWindowFocus: false },
  },
})

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', ...dashboard },
      { path: '/compare', ...compare },
      { path: '/rules', ...rules },
      { path: '/transactions', ...transactions },
      { path: '/import', ...importPage },
      { path: '/projection', ...projection },
      { path: '/assets/:symbol', ...assetDetail },
      { path: '*', element: <Muted>페이지를 찾을 수 없습니다.</Muted> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <CurrencyProvider>
        <ThemeProvider>
          <RouterProvider router={router} />
        </ThemeProvider>
      </CurrencyProvider>
    </QueryClientProvider>
  </StrictMode>,
)
