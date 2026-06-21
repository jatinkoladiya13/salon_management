from django.db import models
from salon_management.behaviours import DateMixin
import uuid

class   SubscriptionPlan(DateMixin, models.Model):
    INTERVAL_CHOICES = (
        ('month', 'Month'),
        ('year', 'Year'),
        ("trial", "trial"),
    )

    plan_type_choice = (
        ("free", "Free"),
        ("pro", "Pro"),
        ("enterprise", "Enterprise"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    features = models.JSONField(blank=True, null=True)

    stripe_price = models.ForeignKey(
        "djstripe.Price",
        on_delete=models.SET_NULL,
        related_name="subscription_plans",
        null=True,
    )
    interval = models.CharField(max_length=20, null=True, blank=True, default="trial", choices=INTERVAL_CHOICES,)
    plan_type = models.CharField(choices=plan_type_choice, default="free", max_length=10)

    is_active = models.BooleanField(default=True)
   
    class Meta:
        db_table = "subscription_plan"
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"
        ordering = ("id",)
        indexes = [models.Index(fields=["name"])]

    def __str__(self) -> str:
        return self.name if self.name else str(self.id)    