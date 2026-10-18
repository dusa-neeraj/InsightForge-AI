import pytest

from config import settings
from services import rate_limit


@pytest.fixture(autouse=True)
def no_rate_limits(monkeypatch):
    """Tests create many datasets quickly, so rate limiting is off unless a test turns it on."""
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    rate_limit.limiter.reset()