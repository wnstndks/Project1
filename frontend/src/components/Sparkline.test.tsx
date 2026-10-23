import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Sparkline } from './Sparkline'

function polyline(container: HTMLElement) {
  const el = container.querySelector('polyline')
  if (!el) throw new Error('no polyline rendered')
  return el
}

describe('Sparkline', () => {
  it('draws one point per close inside the box', () => {
    const { container } = render(<Sparkline closes={[10, 12, 11, 15, 14]} width={96} height={32} />)
    const points = polyline(container).getAttribute('points')!.split(' ')
    expect(points).toHaveLength(5)
    for (const p of points) {
      const [x, y] = p.split(',').map(Number)
      expect(x).toBeGreaterThanOrEqual(0)
      expect(x).toBeLessThanOrEqual(96)
      expect(y).toBeGreaterThanOrEqual(0)
      expect(y).toBeLessThanOrEqual(32)
    }
    // First point at the left edge, last at the right edge; the max (15) is the highest (smallest y).
    expect(points[0].startsWith('1.5,')).toBe(true)
    expect(points[4].startsWith('94.5,')).toBe(true)
    const ys = points.map((p) => Number(p.split(',')[1]))
    expect(Math.min(...ys)).toBe(ys[3])
  })

  it('colors a rise red and a fall blue (Korean convention), flat gray', () => {
    const up = render(<Sparkline closes={[1, 3, 2, 4]} />)
    expect(polyline(up.container).getAttribute('stroke')).toBe('var(--gain-mark)')
    const down = render(<Sparkline closes={[4, 5, 3, 1]} />)
    expect(polyline(down.container).getAttribute('stroke')).toBe('var(--loss-mark)')
    const flat = render(<Sparkline closes={[2, 3, 1, 2]} />)
    expect(polyline(flat.container).getAttribute('stroke')).toBe('var(--muted)')
  })

  it('is decorative and keeps its slot when there is no data', () => {
    const { container } = render(<Sparkline closes={[7]} width={96} height={32} />)
    expect(container.querySelector('svg')).toBeNull()
    const slot = container.firstElementChild as HTMLElement
    expect(slot.getAttribute('aria-hidden')).toBe('true')
    expect(slot.style.width).toBe('96px')
    expect(slot.style.height).toBe('32px')
    const drawn = render(<Sparkline closes={[1, 2]} />)
    expect(drawn.container.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
  })
})
