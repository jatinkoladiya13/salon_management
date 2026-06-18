from django_tenants.models import TenantMixin, DomainMixin
from django.db import models
from account.models import User
from salonDetails.models import SalonDetails
from subscription.models import SubscriptionPlan

from salon_management.behaviours import DateMixin

import uuid

# Create your models here.

class Tenant(TenantMixin, DateMixin):
    subscription_status_choices = (
        ("inactive", "inactive"),
        ("active", "active"),
        ("cancelled", "cancelled"),
        ("expired", "expired"),
        ("past_due", "Past Due"),
        ("trial", "Trial"),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)

    salonDetails = models.OneToOneField(
        SalonDetails, 
        on_delete=models.CASCADE, 
        related_name="salong_for_tenant", 
        blank=True, 
        null=True
    )
    
    stripe_customer_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
    )
    stripe_subscription_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True
    )
    
    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,  
        blank=True,
        related_name="tenant",
    )
    subscription_end_date =  models.DateTimeField(blank=True, null=True)
    subscription_status = models.CharField(
        choices=subscription_status_choices, default="inactive", max_length=20
    )

    auto_create_schema = True
    auto_drop_schema = True

    def __str__(self):
        return f"{self.name} ({self.subscription_status})"

class Domain(DomainMixin):
    pass

