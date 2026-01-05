from django.db import models
from .subscription_plan import SubscriptionPlan


class SubscriptionPlanType(models.Model):
    plan_type_choice = (
        ("basic", "Basic"),
        ("pro", "Pro"),
        ("enterprise", "Enterprise"),
    )

    plan_type = models.CharField(choices=plan_type_choice, max_length=10)
    subscription_plans = models.ManyToManyField(
        SubscriptionPlan, related_name="subscription_plan_type"
    )

    class Meta:
        db_table = "subscription_plan_type"
        verbose_name = "Subscription Plan Type"
        verbose_name_plural = "Subscription Plan Type"

    def __str__(self) -> str:
        return self.plan_type

