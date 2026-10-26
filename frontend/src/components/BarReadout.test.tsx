import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { BarReadout } from './BarReadout'

const fmt = (v: number) => `${v.toLocaleString('en-US')}원`
const bar = { date: '2026-10-21', open: 99, high: 104, low: 98, close: 101, volume: 25_000_000 }
const valueOf = (label: string) => screen.getByText(label).nextSibling

describe('BarReadout', () => {
  afterEach(cleanup)

  it('lists the day figures with the move against the previous close', () => {
    render(<BarReadout bar={bar} prevClose={102} ma={[{ n: 20, value: 100.5 }, { n: 60, value: null }]} format={fmt} />)
    expect(valueOf('시가')).toHaveTextContent('99원')
    expect(valueOf('고가')).toHaveTextContent('104원')
    expect(valueOf('저가')).toHaveTextContent('98원')
    expect(valueOf('종가')).toHaveTextContent('101원')
    const change = screen.getByText(/−1원/)
    expect(change).toHaveClass('text-loss')
    expect(change).toHaveTextContent('▼−1원(−0.98%)')
    expect(valueOf('거래량')).toHaveTextContent('2,500만')
    expect(valueOf('20일 평균')).toHaveTextContent('100.5원')
    // An average whose window has not filled yet is left out rather than shown as 0.
    expect(screen.queryByText('60일 평균')).toBeNull()
  })

  it('marks an up day red with ▲ and a plus sign', () => {
    render(<BarReadout bar={{ ...bar, close: 103 }} prevClose={100} ma={[]} format={fmt} />)
    const change = screen.getByText(/\+3원/)
    expect(change).toHaveClass('text-gain')
    expect(change).toHaveTextContent('▲+3원(+3.00%)')
  })

  it('drops the change figure without a previous close instead of showing a flat zero', () => {
    render(<BarReadout bar={bar} ma={[]} format={fmt} />)
    expect(valueOf('종가')).toHaveTextContent('101원')
    expect(screen.queryByText('전일 대비')).toBeNull()
  })
})
