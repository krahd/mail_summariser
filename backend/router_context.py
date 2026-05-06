from __future__ import annotations

import sys
from types import ModuleType


def get_app_module() -> ModuleType:
    """Return the active app module.

    Tests sometimes import and patch top-level `app`, while runtime imports
    `backend.app`. Prefer the top-level module when present so routers observe
    test-time state mutations.
    """

    if 'app' in sys.modules:
        return sys.modules['app']

    from backend import app as app_module  # pylint: disable=import-outside-toplevel

    return app_module
