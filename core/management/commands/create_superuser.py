import os

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import CustomGroup
from core.constants import SUPERADMIN_GROUP_NAME
from decouple import config

User = get_user_model()


class Command(BaseCommand):
    help = "Create superuser from environment variables"

    def handle(self, *args, **kwargs):
        username = config("SUPERUSER_USERNAME")
        email = config("SUPERUSER_EMAIL")
        password = config("SUPERUSER_PASSWORD")

        if not all([username, email, password]):
            self.stdout.write(
                self.style.ERROR(
                    "SUPERUSER_USERNAME, SUPERUSER_EMAIL, and SUPERUSER_PASSWORD must be set."
                )
            )
            return

        if User.objects.filter(email=email, is_superuser=True).exists():
            self.stdout.write(
                self.style.WARNING(f"Superuser with email '{email}' already exists.")
            )
            return

        group, created = CustomGroup.objects.get_or_create(
            name=SUPERADMIN_GROUP_NAME,
            defaults={"level": 1},
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"Group '{SUPERADMIN_GROUP_NAME}' created."))
        else:
            self.stdout.write(self.style.WARNING(f"Group '{SUPERADMIN_GROUP_NAME}' already exists."))

        user = User.objects.create_superuser( 
            username=username,
            email=email,
            password=password,
        )

        user.groups.add(group)  

        self.stdout.write(
            self.style.SUCCESS(f"Superuser '{username}' created and added to '{SUPERADMIN_GROUP_NAME}'.")
        )