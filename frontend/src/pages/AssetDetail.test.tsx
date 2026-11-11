import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/client'
import { AssetDetail } from './AssetDetail'

const state: { infoError: unknown } = { infoError: null }

// Only the queries the page runs before it knows the symbol; nothing below the early return is drawn.
vi.mock('../api/hooks', () => ({
  useAssetInfo: () => ({ data: undefined, error: state.infoError }),
  useHoldings: () => ({ data: [] }),
  useUsdKrw: () => ({ data: undefined }),
  useConvertCurrency: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useHistory: () => ({ data: undefined }),
  useForecast: () => ({ data: undefined }),
}))

const renderAt = (symbol: string) =>
  render(
    <MemoryRouter initialEntries={[`/assets/${symbol}`]}>
      <Routes>
        <Route path="/assets/:symbol" element={<AssetDetail />} />
      </Routes>
    </MemoryRouter>,
  )

afterEach(cleanup)

describe('AssetDetail: a symbol the server will not show', () => {
  it("on the demo, explains in the server's words and offers the way back home", () => {
    const detail = '데모에서는 데모 장부에 있는 종목만 볼 수 있어요'
    state.infoError = new ApiError(403, detail, 'demo_symbol_not_allowed')
    renderAt('ZZZ')
    expect(screen.getByRole('status')).toHaveTextContent(detail)
    expect(screen.getByRole('link', { name: '홈에서 데모 종목 보기 →' })).toHaveAttribute('href', '/')
    // Guidance, not a failure: no alert box.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps the error box for every other failure', () => {
    state.infoError = new ApiError(404, "Unknown symbol 'ZZZ'")
    renderAt('ZZZ')
    expect(screen.getByRole('alert')).toHaveTextContent("Unknown symbol 'ZZZ'")
    expect(screen.queryByRole('link', { name: '홈에서 데모 종목 보기 →' })).not.toBeInTheDocument()
  })
})
