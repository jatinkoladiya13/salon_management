from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.signing import Signer, BadSignature
from django.utils.http import base36_to_int, int_to_base36
from datetime import datetime, timedelta, timezone


class CustomPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    def make_token(self, user):
        
        # Generate token using base class method
        token = super().make_token(user)

        token_expires = datetime.now(timezone.utc) + timedelta(minutes=120)

        signer = Signer()
        signed_data = signer.sign(
            f"{user.email}-{int(token_expires.timestamp())}"
        )
         
        token += f'--{signed_data}'

        return token
    
    def check_token(self, user, token):
        if not token:
            return False

        try:
            token, signed_data = token.rsplit('--', 1)
        except ValueError:
            return False

        signer = Signer()
        try:
            # rsplit on the last '-' only: the payload is "<email>-<expiry>" and
            # plenty of real addresses contain a hyphen, which used to make the
            # unpack fail for those users.
            email, token_expiry = signer.unsign(signed_data).rsplit('-', 1)
        except (BadSignature, ValueError):
            return False

        if email != user.email:
            return False

        try:
            token_expiry = int(token_expiry)
        except (TypeError, ValueError):
            return False

        token_expiry = datetime.fromtimestamp(token_expiry, tz=timezone.utc)

        if token_expiry <= datetime.now(timezone.utc):
            return False

        return super().check_token(user, token)