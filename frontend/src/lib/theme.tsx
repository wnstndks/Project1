/* oxlint-disable react/only-export-components -- context provider and its hooks live together */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

/**
 * Color theme. Light is the default, like Toss, whatever the OS prefers; `system` follows the OS.
 * The choice lives in `data-theme` on <html>, which index.css keys its dark tokens on, and in
 * localStorage so it survives reloads. index.html presets the attribute before the first paint
 * from the same key, so there is no flash of the wrong theme; this provider then keeps it in sync.
 */
export type Theme = 'light' | 'dark' | 'system'

export const THEMES: readonly Theme[] = ['light', 'dark', 'system'] as const
export const DEFAULT_THEME: Theme = 'light'
export const THEME_STORAGE_KEY = 'asset-manager.theme'

export function isTheme(v: unknown): v is Theme {
  return typeof v === 'string' && (THEMES as readonly string[]).includes(v)
}

export function readStoredTheme(): Theme {
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY)
    return isTheme(v) ? v : DEFAULT_THEME
  } catch {
    return DEFAULT_THEME
  }
}

/** Writes the choice to <html data-theme>, where the stylesheet reads it. */
export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
}

const ThemeContext = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({
  theme: DEFAULT_THEME,
  setTheme: () => {},
})

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setState] = useState<Theme>(readStoredTheme)
  useEffect(() => applyTheme(theme), [theme])
  const setTheme = (t: Theme) => {
    setState(t)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, t)
    } catch {
      // Private mode or blocked storage: the choice just won't persist.
    }
  }
  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}
