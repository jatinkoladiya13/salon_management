from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from tenant.models import Tenant, Domain
from decouple import config

class Command(BaseCommand):
    help = "Create template schema tenant"

    TEMPLATE_SCHEMA = "template_schema"
    TEMPLATE_DOMAIN = f"template_schema.{config('HOST_URI', default='localhost')}"

    def handle(self, *args, **options):

        tenant = Tenant.objects.filter(
            schema_name=self.TEMPLATE_SCHEMA
        ).first()

        if tenant:
            self.stdout.write(
                self.style.WARNING(
                    f"Schema '{self.TEMPLATE_SCHEMA}' already exists."
                )
            )
            return

        tenant = Tenant.objects.create(
            schema_name=self.TEMPLATE_SCHEMA,
            name="Template Schema",
            subscription_status="active",
        )

        Domain.objects.get_or_create(
            domain=self.TEMPLATE_DOMAIN,
            defaults={
                "tenant": tenant,
                "is_primary": True,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Schema '{self.TEMPLATE_SCHEMA}' created successfully."
            )
        )

        with schema_context(self.TEMPLATE_SCHEMA):
            self.stdout.write(
                self.style.SUCCESS(
                    "Switched to template schema."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Template schema setup completed."
            )
        )