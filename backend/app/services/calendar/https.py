import ssl
from functools import lru_cache

import certifi


@lru_cache(maxsize=1)
def google_ssl_context() -> ssl.SSLContext:
    """Return a verified TLS context that works in local Python installations."""
    return ssl.create_default_context(cafile=certifi.where())
