// Presets the saved theme on <html> before the first paint, so a dark-theme user never sees a
// light flash. Same storage key as src/lib/theme.tsx; light stays the default.
//
// A file of its own, not an inline <script>: the deployed app sends
// `Content-Security-Policy: script-src 'self'`, which refuses inline scripts. index.html loads it
// from <head> without async/defer/module, so it runs before the body is drawn. It is served as
// is (not bundled), so it stays a plain script with no imports.
try {
  var theme = localStorage.getItem('asset-manager.theme')
  if (theme === 'dark' || theme === 'system') document.documentElement.dataset.theme = theme
} catch {
  // Private mode or blocked storage: keep the default.
}
