"""WebSocket origin validation.

``channels.security.websocket.AllowedHostsOriginValidator`` reuses
``settings.ALLOWED_HOSTS`` (a *Host* header allowlist) to validate the *Origin*
header, and it rejects every connection that carries no Origin header at all
unless ``ALLOWED_HOSTS`` contains ``"*"``. Non-browser clients (mobile apps,
Postman, wscat, python-websockets) never send an Origin, so they were being
rejected before reaching the consumer.

This module keeps the cross-site protection that matters for browsers while
letting those clients through, and logs every rejection with the offending
origin so failures are diagnosable from the container logs.
"""

import logging

from channels.security.websocket import OriginValidator
from django.conf import settings

logger = logging.getLogger(__name__)


class LoggingOriginValidator(OriginValidator):
    """``OriginValidator`` that can accept origin-less clients and logs denials."""

    def __init__(self, application, allowed_origins, allow_missing_origin=False):
        super().__init__(application, allowed_origins)
        self.allow_missing_origin = allow_missing_origin

    def valid_origin(self, parsed_origin):
        # ``parsed_origin`` is None when the header is absent or undecodable.
        # A present-but-opaque origin ("null", from a sandboxed iframe or
        # file://) parses into a ResultParse with no hostname; treat both the
        # same way.
        if parsed_origin is None or parsed_origin.hostname is None:
            if self.allow_missing_origin or "*" in self.allowed_origins:
                return True
            logger.warning(
                "WebSocket rejected: no usable Origin header "
                "(set CHANNELS_ALLOW_MISSING_ORIGIN=True for non-browser clients)"
            )
            return False

        if self.validate_origin(parsed_origin):
            return True

        logger.warning(
            "WebSocket rejected: Origin %r not in CHANNELS_ALLOWED_ORIGINS %r",
            parsed_origin.geturl(),
            self.allowed_origins,
        )
        return False


def SettingsOriginValidator(application):
    """Build the validator from ``CHANNELS_ALLOWED_ORIGINS``."""
    return LoggingOriginValidator(
        application,
        settings.CHANNELS_ALLOWED_ORIGINS,
        allow_missing_origin=settings.CHANNELS_ALLOW_MISSING_ORIGIN,
    )
