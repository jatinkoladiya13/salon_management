import logging

from django.core.exceptions import (
    ObjectDoesNotExist,
    ValidationError as DjangoValidationError,
)
from django.db import IntegrityError
from django.http import Http404

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def _envelope(message, status_code):
    return Response(
        {
            "error": True,
            "data": {},
            "message": message,
        },
        status=status_code,
    )


def custom_exception_handler(exc, context):
    """
    Wrap every error in the project's ``{error, data, message}`` envelope.

    Anything DRF already understands keeps its own status code. The remaining
    cases are mapped explicitly so a genuine server fault is reported as 500 and
    logged. Returning 400 for an unexpected crash - the previous behaviour -
    both hid the fault from monitoring and echoed internal detail, such as SQL
    text, back to the caller.
    """
    response = exception_handler(exc, context)

    if response is not None:
        return _envelope(getattr(exc, "detail", str(exc)), response.status_code)

    # Django-level equivalents of DRF exceptions that never reached the DRF map.
    if isinstance(exc, (Http404, ObjectDoesNotExist)):
        return _envelope(NotFound.default_detail, status.HTTP_404_NOT_FOUND)

    if isinstance(exc, DjangoValidationError):
        return _envelope(
            getattr(exc, "message_dict", None) or exc.messages,
            status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, IntegrityError):
        logger.warning("Integrity error on %s", context.get("request"), exc_info=exc)
        return _envelope(
            "This operation conflicts with existing data.",
            status.HTTP_409_CONFLICT,
        )

    logger.exception("Unhandled exception in %s", context.get("view"), exc_info=exc)
    return _envelope(
        "Something went wrong. Please try again later.",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
