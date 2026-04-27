"""
Pytest infrastructure — auto-reset shared state between tests.
"""

import os
import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Reset rate limit state before each test to prevent cross-test contamination."""
    from app import dependencies
    if hasattr(dependencies, "_rate_state") and dependencies._rate_state is not None:
        dependencies._rate_state = dependencies.RateLimitState()
    yield


@pytest.fixture(autouse=True)
def _clean_test_presets():
    """Clean test presets file before each test."""
    paths = [
        "/tmp/test_presets.json",
        "/tmp/integration_test_presets.json",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    yield
    for p in paths:
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
