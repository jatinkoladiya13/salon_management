
import pyotp
import qrcode
import base64
from io import BytesIO


def generate_secret():
    return pyotp.random_base32()

def get_totp(secret):
    return pyotp.TOTP(secret)

def generate_qr_code(username, secret):
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name="MyApp"
    )

    qr = qrcode.make(uri)
    buffer = BytesIO()
    qr.save(buffer)
    return base64.b64encode(buffer.getvalue()).decode()


def fun_valid_password(value):

    if " " in value:
        return "Password should not contain any space."
   
    # password should not contain at least one digit, one uppercase, one lowercase and one special character
    if not any(char.isdigit() for char in value):
        return "Password should contain at least one digit."
    
    if not any(char.isupper() for char in value):
        return "Password should contain at least one uppercase."
    
    if not any(char.islower() for char in value):
        return "Password should contain at least one lowercase."
    
    if not any(char in '!@#$%^&*()_+}{":?><,./;' for char in value):
        return "Password should contain at least one special character."

    return None
    