from __future__ import annotations

# conftest for tests/e2e: enables collection of the e2e folder only when the
# user explicitly points pytest at tests/e2e. The root tests/conftest.py
# installs a pytest_ignore_collect hook that returns True (skip) for any file
# under tests/e2e unless the CLI args show the user opted in. This conftest
# exists so that `pytest tests/e2e` collects the e2e tests via the hook's
# allow-list branch.
