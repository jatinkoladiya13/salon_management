from django.db import models
from dateutil.relativedelta import relativedelta
from django.utils import timezone

class SubscriptionPlan(models.Model):
    INTERVAL_CHOICES = (
        ('month', 'Month'),
        ('year', 'Year'),
        ("trial", "trial"),
    )
    name = models.CharField(max_length=255, blank=True, null=True)
    slug = models.SlugField(max_length=100, unique=True)
    stripe_price = models.ForeignKey(
        "djstripe.Price",
        on_delete=models.SET_NULL,
        related_name="subscription_plans",
        null=True,
    )
      
    description = models.TextField(null=True, blank=True)
    interval = models.CharField(max_length=20, null=True, blank=True, choices=INTERVAL_CHOICES,)

    is_active = models.BooleanField(default=True)
    credits_minutes = models.IntegerField(default=0)
    created_on = models.DateTimeField(auto_now_add=True)
    

    def __str__(self):
        return self.slug

    class Meta:
        db_table = "subscription_plan"
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"
        ordering = ("id",)
        indexes = [models.Index(fields=["name"])]