"""Read-only analysis jobs that never acquire an API route (ADR-030 Decision 8).

This package holds offline analysis over data the service already stores. It is
imported by scripts and by tests, never by ``app.py`` or any router: a route is a
data-egress path, and the data this package aggregates is exactly the kind that
must not gain one.
"""
