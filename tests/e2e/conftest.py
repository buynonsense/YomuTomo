from __future__ import annotations

# conftest for tests/e2e: re-enable collection of the e2e folder.
# The root tests/conftest.py sets collect_ignore_glob = ['e2e/*'] so e2e tests
# don't run during normal `pytest`. When the user explicitly points pytest at
# tests/e2e, this conftest clears the ignore list so the e2e tests run.
collect_ignore_glob: list[str] = []
