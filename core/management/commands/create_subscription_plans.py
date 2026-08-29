from django.core.management.base import BaseCommand
from subscription.models import SubscriptionPlan


class Command(BaseCommand):
    help = "Create default subscription plans"

    def handle(self, *args, **kwargs):
        plans = [
            {
                "name": "Free Plan",
                "description": "Basic free plan for new users",
                "plan_type": "free",
                "interval": "trial",
                "is_active": True,
                "features": {
                    "appointments": 5,
                    "staff_members": 1,
                    "clients": 10,
                    "online_booking": False,
                    "sms_reminders": False,
                },
            },
            {
                "name": "Pro Plan",
                "description": "Professional plan with advanced features",
                "plan_type": "pro",
                "interval": "month",
                "is_active": True,
                "features": {
                    "appointments": 500,
                    "staff_members": 5,
                    "clients": 500,
                    "online_booking": True,
                    "sms_reminders": True,
                    "analytics": True,
                },
            },
            {
                "name": "Enterprise Plan",
                "description": "Enterprise plan with full features",
                "plan_type": "enterprise",
                "interval": "year",
                "is_active": True,
                "features": {
                    "appointments": "unlimited",
                    "staff_members": "unlimited",
                    "clients": "unlimited",
                    "online_booking": True,
                    "sms_reminders": True,
                    "analytics": True,
                    "api_access": True,
                    "custom_branding": True,
                    "priority_support": True,
                },
            },
        ]

        for plan_data in plans:
            plan, created = SubscriptionPlan.objects.get_or_create(
                name=plan_data["name"],
                defaults={
                    "description": plan_data.get("description"),
                    "plan_type": plan_data.get("plan_type", "free"),
                    "interval": plan_data.get("interval", "trial"),
                    "is_active": plan_data.get("is_active", True),
                    "features": plan_data.get("features", {}),
                },
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created subscription plan: {plan.name}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"✗ Subscription plan already exists: {plan.name}")
                )

        self.stdout.write(
            self.style.SUCCESS("Subscription plans setup completed.")
        )
