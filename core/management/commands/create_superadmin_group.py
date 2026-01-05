from django.core.management.base import BaseCommand
from core.constants import SUPERADMIN_GROUP_NAME
from core.models import CustomGroup, RoleBasePermissions, RoleBasePermissionsStatus
from django_tenants.utils import schema_context
from core.constants import *
from django_tenants.utils import get_tenant_model


GROUPS = [SUPERADMIN_GROUP_NAME]

FALSE_PERMISSIONS_FOR_SUPERADMIN = []

class Command(BaseCommand):
    help = "Creates Superadmin Group"

    def add_arguments(self, parser):
        parser.add_argument(
            "schema_name", type=str, nargs="?", help="schema name"
        )

    def obj_created(self):
        for group in GROUPS:
            group, created = CustomGroup.objects.get_or_create(
                name=group, level=1
            )

            all_permissions_obj = RoleBasePermissions.objects.all()
            for permission_obj in all_permissions_obj:
                (
                    permission,
                    created,
                ) = RoleBasePermissionsStatus.objects.get_or_create(
                    group_id=group.id, role_permission_id=permission_obj.id
                )
                permission.status = (
                    False
                    if permission_obj.name in FALSE_PERMISSIONS_FOR_SUPERADMIN
                    else True
                )
                permission.save()

    def handle(self, *args, **options):
        schema_name = options["schema_name"]

        if not schema_name:
            schema_name = input("Enter Tenant Schema ('?' to list schemas): ")

        Tenant = get_tenant_model()
        
        try:
            # Switch to the specified schema
            tenant = Tenant.objects.get(schema_name=schema_name)
            with tenant:
                self.obj_created()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created TenantAdmin Group for tenant {schema_name}"
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
                    f"Error in Created TenantAdmin Group :- {str(e)}"
                )
            )             
