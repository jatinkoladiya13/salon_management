from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from account.custom_token import CustomPasswordResetTokenGenerator
from salon_management.celery import send_mail
from decouple import config
# from account.models.

def send_reset_password_email(user, schema_name):
    token = CustomPasswordResetTokenGenerator().make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))

    url = f"{config('HTTP_PROXY')}{schema_name}.{config('HOST_URI')}/forgot-password/reset-password"

    subject = "Password reset for Expepriense AI"

    message = render_to_string(
        "accounts/password_reset_email.html",
        {
            "url": url,
            "uid": uid ,
            "token": token,
        },
    )
    
    send_mail.apply_async(args=[subject, message, user.email, "html"])

