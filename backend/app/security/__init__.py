"""Access control for a deployed instance (DECISIONS.md D-035).

Single-account login with signed session cookies, a read-only demo mode, per-IP request
limits and security headers. Everything is standard library plus Starlette; this package
never imports a provider, places no orders and reads no account data.
"""
