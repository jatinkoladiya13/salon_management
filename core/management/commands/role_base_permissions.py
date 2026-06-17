from django.core.management.base import BaseCommand
from core.models import RoleBasePermissions
from core.constants import *
from django_tenants.utils import get_tenant_model

PERMISSIONS = [
    {
        "name": READ_SALON_DETAILS,
        "text": "For list all the salon details",
    },
    {
        "name": CREATE_SALON_DETAILS,
        "text": "For create new salon details",
    },
    {
        "name": UPDATE_SALON_DETAILS,
        "text": "For update the salon details",
    },
    {
        "name": DELETE_SALON_DETAILS,
        "text": "For delete the customer details",
    },

    {"name": READ_GROUPS, "text": "For list all the roles"},
    {"name": CREATE_GROUPS, "text": "For create new roles"},
    {"name": UPDATE_GROUPS, "text": "For update the role"},
    {"name": DELETE_GROUPS, "text": "For delete the role"},

    {
        "name": READ_PERMISSIONS_STATUS,
        "text": "For read the all permissions with role and status",
    },
    {
        "name": UPDATE_PERMISSIONS_STATUS,
        "text": "For update status of the permissions for perticular role",
    },

    {
        "name": READ_OWN_ACCOUNT_ONLY,
        "text": "For only get own account details",
    },
    {
        "name": UPDATE_OWN_ACCOUNT_ONLY,
        "text": "For only update own account details",
    },
     {
        "name": DELETE_OWN_ACCOUNT_ONLY,
        "text": "For only delete own account details",
    },

    {
        "name":READ_USERS_ACCOUNT,
        "text":"For get uses account"
    },
    {
        "name": CREATE_USERS_ACCOUNT,
        "text": "For register new user",
    },
    {
        "name": UPDATE_USERS_ACCOUNT,
        "text": "For update user account details",
    },
    {
        "name": DELETE_USERS_ACCOUNT,
        "text": "For delete user account",
    },

    {
        "name": READ_STAFF_USERS_ACCOUNT_ONLY,
        "text": "get users only which staff than login user",
    },
    {
        "name": UPDATE_STAFF_USERS_ACCOUNT_ONLY,
        "text": "update users only which staff than login user",
    },
    {
        "name": DELETE_STAFF_USERS_ACCOUNT_ONLY,
        "text": "delete users only which staff than login user",
    },
    {
        "name": CREATE_STAFF_USERS_ACCOUNT_ONLY,
        "text": "create users only which staff than login user",
    },
    {
        "name": MANAGE_SUBSCRIPTION,
        "text": "For manage subscription",
    },
]

class Command(BaseCommand):
    help = "Create permissions"

    def add_arguments(self, parser):
        parser.add_argument(
            "schema_name", type=str, nargs="?", help="schema name"
        )

    def obj_created(self):
        for permission in PERMISSIONS:
            (   
                permission_obj,
                created,
            ) = RoleBasePermissions.objects.get_or_create(
                name = permission["name"]
            )
            permission_obj.description = permission["text"]
            permission_obj.save()

    def handle(self, *args, **options):
        schema_name = options["schema_name"]

        if not schema_name:
            schema_name = input("Enter Tenant Schema ('?' to list schemas): ")

        Tenant = get_tenant_model()

        try:
            tenant = Tenant.objects.get(schema_name=schema_name)
            with tenant:
                self.obj_created()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created default Permissions for tenant {schema_name}"
                    )
                ) 
        except Tenant.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"Tenant with schema name {schema_name} does not exist"
                )
            )           

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"Error in Created default Permissions :- {str(e)}"
                )
            )       


