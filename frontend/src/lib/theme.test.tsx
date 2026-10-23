/// <reference types="node" />
import { act, cleanup, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DEFAULT_THEME, readStoredTheme, THEME_STORAGE_KEY, ThemeProvider, useTheme } from './theme'

// Vitest resolves a `.css?raw` import to an empty string, so the stylesheet is read from disk
// (the test runs from the frontend root).
const css = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')

function Probe() {
  const { theme, setTheme } = useTheme()
  return (
    <div>
      <output data-testid="theme">{theme}</output>
      <button type="button" onClick={() => setTheme('dark')}>
        dark
      </button>
      <button type="button" onClick={() => setTheme('system')}>
        system
      </button>
    </div>
  )
}

describe('ThemeProvider', () => {
  afterEach(() => {
    cleanup()
    localStorage.clear()
    delete document.documentElement.dataset.theme
  })

  it('defaults to light, whatever the OS prefers, and writes it to <html data-theme>', () => {
    expect(DEFAULT_THEME).toBe('light')
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('stores a choice and reflects it on <html> at once', () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    act(() => screen.getByText('dark').click())
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    act(() => screen.getByText('system').click())
    expect(document.documentElement.dataset.theme).toBe('system')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system')
  })

  it('still works when storage throws (private mode, blocked site data)', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'QuotaExceededError')
    })
    try {
      expect(readStoredTheme()).toBe('light')
      render(
        <ThemeProvider>
          <Probe />
        </ThemeProvider>,
      )
      expect(document.documentElement.dataset.theme).toBe('light')
      act(() => screen.getByText('dark').click())
      // The choice applies for this page even though it cannot be remembered.
      expect(screen.getByTestId('theme')).toHaveTextContent('dark')
      expect(document.documentElement.dataset.theme).toBe('dark')
    } finally {
      getItem.mockRestore()
      setItem.mockRestore()
    }
  })

  it('restores the stored choice and ignores garbage', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    expect(readStoredTheme()).toBe('dark')
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    cleanup()
    localStorage.setItem(THEME_STORAGE_KEY, 'sepia')
    expect(readStoredTheme()).toBe('light')
  })
})

describe('index.css theme tokens', () => {
  const block = (selector: string): string[] => {
    const start = css.indexOf(selector)
    expect(start, `${selector} present`).toBeGreaterThan(-1)
    const open = css.indexOf('{', start)
    const close = css.indexOf('}', open)
    return css
      .slice(open + 1, close)
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
  }

  it('applies dark tokens only on an explicit choice or on system + OS dark, never on OS dark alone', () => {
    expect(css).not.toMatch(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{/)
    expect(css).toMatch(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root\[data-theme='system'\]/)
    expect(css).toMatch(/^:root\[data-theme='dark'\]/m)
  })

  it('keeps the two dark blocks identical, color-scheme included', () => {
    const explicit = block(":root[data-theme='dark']")
    const system = block(":root[data-theme='system']")
    expect(explicit).toContain('color-scheme: dark;')
    expect(explicit).toEqual(system)
    // Every light token has a dark counterpart.
    const light = block(':root {').filter((l) => l.startsWith('--')).map((l) => l.split(':')[0])
    const dark = explicit.filter((l) => l.startsWith('--')).map((l) => l.split(':')[0])
    expect(dark).toEqual(light)
  })
})
