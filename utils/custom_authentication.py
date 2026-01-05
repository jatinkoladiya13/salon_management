from rest_framework_simplejwt import authentication, exceptions
from django.utils.translation import gettext_lazy as _

class CustomJWTAuthentication(authentication.JWTAuthentication):
    def check_schema_name(self, payload, schema_name):
        try:
            payload_schema_name = payload["schema_name"]
        except KeyError:
            raise exceptions.InvalidToken(
                _("Token contained not recognizable user identification")
            ) 

        if payload_schema_name != schema_name:
            raise exceptions.InvalidToken(
                _("Token is invalid"), code="token_not_valid"
            )

        return schema_name

    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)

        self.check_schema_name(
            validated_token.payload, request.tenant.schema_name
        )

        return self.get_user(validated_token), validated_token