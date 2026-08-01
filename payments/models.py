from django.db.models import Q
from django.db import models

import uuid
# Create your models here.

class PaymentProvider(models.TextChoices):
    STRIPE = "stripe", "Stripe"
    RAZORPAY = "razorpay", "Razorpay"
    PAYPAL = "paypal", "PayPal"

class PaymentConfiguration(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(
        max_length=20,
        choices=PaymentProvider.choices
    )

    is_active = models.BooleanField(default=True)

    payment_credentials = models.JSONField(
        blank=True,
        null=True
    )

    webhook_secret = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    currency = models.CharField(
        max_length=10,
        default="INR"
    )

    branding_details = models.JSONField(
        blank=True,
        null=True
    )
    brand_logo = models.ImageField(
        upload_to="payment_branding_logos/",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_configuration"
        verbose_name = "Payment Configuration"
        verbose_name_plural = "Payment Configurations"
    
    def save(self, *args, **kwargs):
        """
        Override the save method to ensure only one payment configuration is active at a time.
        """
        if self.is_active:
            # Deactivate all other configurations
            PaymentConfiguration.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.provider