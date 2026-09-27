from rest_framework.exceptions import APIException
from rest_framework import status
from django.utils.translation import gettext_lazy as _


class BadRequestException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _("something went wrong. please try again later")
    default_code = "bad_request"
