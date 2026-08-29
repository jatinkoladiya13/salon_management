# core/management/commands/setup_project.py

from django.core.management import call_command
from django.core.management.base import BaseCommand

TEMPLATE_SCHEMA = "template_schema"


class Command(BaseCommand):
    help = "Initial project setup"

    def handle(self, *args, **kwargs):
        commands = [
            
            {
                "name": "create_public_tenant",
            },
            {
                "name": "create_superuser",
            },

            {
                "name": "create_template_schema",
            },

            {
                "name": "role_base_permissions",
                "kwargs": {
                    "schema_name": TEMPLATE_SCHEMA
                }
            },

            {
                "name": "create_tenantadmin_group",
                "kwargs": {
                    "schema_name": TEMPLATE_SCHEMA
                }
            },

            {
                "name": "create_staff_group",
                "kwargs": {
                    "schema_name": TEMPLATE_SCHEMA
                }
            },

            {
                "name": "create_user_group",
                "kwargs": {
                    "schema_name": TEMPLATE_SCHEMA
                }
            },

            {
                "name": "create_subscription_plans",
            },
        ]

        for command in commands:
            try:
                self.stdout.write(
                    self.style.WARNING(f"Running {command['name']}...")
                )
                kwargs = command.get("kwargs", {})

                call_command( command["name"], **kwargs)

                self.stdout.write(
                    self.style.SUCCESS(f"{command['name']} completed.")
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"{command['name']} failed: {str(e)}"
                    )
                )
                raise

        self.stdout.write(
            self.style.SUCCESS(
                "Project setup completed successfully."
            )
        )