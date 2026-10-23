import { describe, expect, it } from 'vitest'

import { isSuspiciousCost } from './holdings'

describe('isSuspiciousCost', () => {
  it('accepts ordinary winners and losers', () => {
    expect(isSuspiciousCost(100, 150)).toBe(false)
    expect(isSuspiciousCost(100, 10)).toBe(false) // -90%, still plausible
    expect(isSuspiciousCost(10, 150)).toBe(false) // 15x gain
  })
  it('flags costs 20x away from the price either way', () => {
    expect(isSuspiciousCost(7.89, 250)).toBe(true) // return % read as the price
    expect(isSuspiciousCost(6000, 250)).toBe(true) // won amount read as the price
  })
  it('ignores zero or missing values', () => {
    expect(isSuspiciousCost(0, 100)).toBe(false)
    expect(isSuspiciousCost(100, 0)).toBe(false)
  })
})
