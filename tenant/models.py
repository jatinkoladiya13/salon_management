from django_tenants.models import TenantMixin, DomainMixin
from django.db import models
from account.models import User
from salonDetails.models import SalonDetails
from subscription.models import SubscriptionPlan
# Create your models here.

class Tenant(TenantMixin):
    subscription_status_choices = (
        ("inactive", "inactive"),
        ("active", "active"),
        ("cancelled", "cancelled"),
        ("expired", "expired"),
    )
    name = models.CharField(max_length=100)
    subscription_end_date = models.DateField(blank=True, null=True)

    salonDetails = models.OneToOneField(SalonDetails, on_delete=models.CASCADE, related_name="salong_for_tenant", blank=True, null=True)
    stripe_customer_id = models.CharField(
        null=True, unique=True, max_length=100
    )  
 
    subscription_status = models.CharField(
        choices=subscription_status_choices, default="inactive", max_length=20
    )
    stipe_subscription_id = models.CharField(max_length=100, blank=True, null=True)
    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tenant",
    )
    
    trial_completed = models.BooleanField(default=False)
    trial_end_date = models.DateField(blank=True, null=True)
    
    created_on = models.DateField(auto_now_add=True)
    auto_create_schema = True
    auto_drop_schema = True

    def __str__(self):
        return f"{self.name} ({self.subscription_status})"

class Domain(DomainMixin):
    pass

