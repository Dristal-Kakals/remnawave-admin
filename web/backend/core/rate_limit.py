"""Rate limiting configuration for web panel.

Uses Redis as storage backend when REDIS_URL is configured,
otherwise falls back to in-memory storage.

Provides granular per-endpoint rate limits via decorators.
"""
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Create limiter with default rate (global fallback)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],
    storage_uri=None,  # in-memory by default, upgraded to Redis in configure_limiter()
)

# ── Per-endpoint rate limit presets ──────────────────────────
# These are applied via @limiter.limit() decorators on endpoints.

RATE_AUTH = "10/minute"          # login, register, refresh
RATE_MUTATIONS = "60/minute"     # create, update, delete
RATE_READ = "120/minute"         # list, detail endpoints
RATE_ANALYTICS = "30/minute"     # heavy analytics queries
RATE_EXPORT = "10/minute"        # CSV/JSON export (potentially large)
RATE_BULK = "10/minute"          # bulk operations


def configure_limiter(redis_url: str | None = None) -> None:
    """Upgrade limiter storage to Redis for distributed rate limiting.

    Called during app startup if REDIS_URL is available.
    """
    if not redis_url:
        return
    try:
        from limits.storage import storage_from_string
        limiter._storage_uri = redis_url
        limiter._storage = storage_from_string(redis_url)
        logger.info("Rate limiter upgraded to Redis backend")
    except Exception as e:
        logger.warning("Failed to configure Redis rate limiter: %s", e)
