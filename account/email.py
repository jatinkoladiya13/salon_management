from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
import logging
from account.custom_token import CustomPasswordResetTokenGenerator
from salon_management.celery import send_mail
from decouple import config
# from account.models.

logger = logging.getLogger(__name__)

def send_reset_password_email(user, schema_name):
    logger.info("=" * 50)
    logger.info(f"Generating password reset token for user: {user.id} - {user.email}")
    
    try:
        token = CustomPasswordResetTokenGenerator().make_token(user)
        logger.debug(f"Token generated successfully")
        
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        logger.debug(f"UID encoded: {uid}")
        
        logger.info(f"Building password reset URL for schema: {schema_name}")
        url = f"{config('HTTP_PROXY')}{schema_name}.{config('HOST_URI')}/forgot-password/reset-password"
        logger.debug(f"Reset URL: {url}")

        subject = "Password reset for Expepriense AI"
        logger.info(f"Subject: {subject}")

        logger.info(f"Rendering password reset email template")
        message = render_to_string(
            "accounts/password_reset_email.html",
            {
                "url": url,
                "uid": uid ,
                "token": token,
            },
        )
        logger.debug(f"Email template rendered successfully")
        
        logger.info(f"Queuing email to Celery for delivery to: {user.email}")
        send_mail.apply_async(args=[subject, message, user.email, "html"])
        logger.info(f"Email task queued successfully for: {user.email}")
        
    except Exception as e:
        logger.error(f"Failed to send reset password email for user {user.id}: {str(e)}", exc_info=True)
        raise
    finally:
        logger.info("=" * 50)

