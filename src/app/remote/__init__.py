"""Remote hook bridge: a host-side TCP broker and the thin client that talks to it.

Containers (e.g. a sandboxed agent) cannot share the WAL-mode SQLite database with the
host across the Docker Desktop VM boundary, so instead of touching the file they forward
the hook to ``agent-hooks server`` running on the host, which performs the normal callback
round-trip locally and returns the decision. See :mod:`app.remote.server` and
:mod:`app.remote.client`.
"""

from __future__ import annotations
