# core/management/commands/create_public_tenant.py

from django.core.management.base import BaseCommand
from decouple import config

from tenant.models import Tenant, Domain


class Command(BaseCommand):
    help = "Create public tenant and public domain for the application"

    def handle(self, *args, **options):
        schema_name = "public"
        tenant_name = "Public Tenant"
        domain_name = config("HOST_URI", default="localhost")

        tenant = Tenant.objects.filter(schema_name=schema_name).first()

        if not tenant:
            tenant = Tenant.objects.create(
                schema_name=schema_name,
                name=tenant_name,
                subscription_status="active",
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Public tenant '{tenant_name}' created."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Public tenant '{tenant_name}' already exists."
                )
            )

    
        domain, created = Domain.objects.get_or_create(
            domain=domain_name,
            defaults={
                "tenant": tenant,
                "is_primary": True,
            },
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Domain '{domain_name}' created."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Domain '{domain_name}' already exists."
                )
            )

        self.stdout.write(
            self.style.SUCCESS("Public tenant setup completed.")
        )