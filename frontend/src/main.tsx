import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode, type ComponentType } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'

import { Layout } from './App'
import { Muted } from './components/ui'
import './index.css'
import { CurrencyProvider } from './lib/currency'

// Pages are split so each chart library (recharts, lightweight-charts) loads only where used.
const page = (load: () => Promise<{ Component: ComponentType }>) => ({ lazy: load })
const dashboard = page(() => import('./pages/Dashboard').then((m) => ({ Component: m.Dashboard })))
const transactions = page(() =>
  import('./pages/Transactions').then((m) => ({ Component: m.Transactions })),
)
const projection = page(() =>
  import('./pages/Projection').then((m) => ({ Component: m.Projection })),
)
const assetDetail = page(() =>
  import('./pages/AssetDetail').then((m) => ({ Component: m.AssetDetail })),
)

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
      { path: '/transactions', ...transactions },
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
        <RouterProvider router={router} />
      </CurrencyProvider>
    </QueryClientProvider>
  </StrictMode>,
)
