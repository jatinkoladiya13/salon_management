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
        try:
            token, signed_data = token.rsplit('--')
        except ValueError:
            print("Token split failed")
            return False   

        signer = Signer()
        try:
            email, token_expiry = signer.unsign(signed_data).split('-')
        except BadSignature as e:
            print(f"Bad Signature: {e}")
            return False
        
        token_expiry = datetime.fromtimestamp(int(token_expiry), tz=timezone.utc)

        if token_expiry <=datetime.now(timezone.utc):
            print("Token expired")
            return False
        
        return super().check_token(user, token)