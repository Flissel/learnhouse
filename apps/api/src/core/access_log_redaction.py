"""Keep secrets out of the uvicorn access log.

uvicorn logs the raw request path including the query string. Invitation
links (``/learning/einladung/<token>``), shared-media tokens and magic-link
query parameters would therefore be readable by anyone with log access.
This filter masks them with ``***`` while keeping route structure and status.
"""

import logging
import re
from typing import Any

MASK = "***"

# Path segments that are followed by a secret: /<keyword>/<secret>
_SECRET_PATH_KEYWORDS = ("einladung", "shared", "invite")
_PATH_RE = re.compile(
    r"(/(?:" + "|".join(_SECRET_PATH_KEYWORDS) + r")/)([^/?#\s]+)"
)

# Query parameters whose values are secrets.
_SENSITIVE_QUERY_KEYS = (
    "token", "code", "invite_code", "mfa_token", "access_token",
    "refresh_token", "id_token", "key", "api_key", "secret", "password",
    "signature", "sig", "state",
)
_QUERY_RE = re.compile(
    r"(?i)([?&](?:" + "|".join(_SENSITIVE_QUERY_KEYS) + r")=)([^&#\s]*)"
)


def redact_path(path: str) -> str:
    """Mask secret path segments and sensitive query values in a request path."""
    path = _PATH_RE.sub(lambda m: m.group(1) + MASK, path)
    return _QUERY_RE.sub(lambda m: m.group(1) + MASK, path)


class AccessLogRedactionFilter(logging.Filter):
    """Rewrite the path argument of uvicorn access records; never drops records."""

    def filter(self, record: logging.LogRecord) -> bool:
        args: Any = record.args
        if isinstance(args, tuple):
            record.args = tuple(
                redact_path(a) if isinstance(a, str) and "/" in a else a for a in args
            )
        return True


def install_access_log_redaction() -> None:
    """Attach the filter to uvicorn's access logger (idempotent)."""
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessLogRedactionFilter) for f in logger.filters):
        logger.addFilter(AccessLogRedactionFilter())
