import { describe, expect, it } from 'vitest'
import { splitShares } from './split'

describe('splitShares', () => {
  it('reads forward, uneven and reverse splits as old → new shares', () => {
    expect(splitShares(10)).toEqual({ from: 1, to: 10 })
    expect(splitShares(1.5)).toEqual({ from: 2, to: 3 })
    expect(splitShares(1 / 30)).toEqual({ from: 30, to: 1 })
  })
})
