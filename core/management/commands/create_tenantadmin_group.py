from core.constants import *
from core.constants import TENANTADMIN_GROUP_NAME
from django_tenants.utils import get_tenant_model
from django.core.management.base import BaseCommand
from core.models import CustomGroup, RoleBasePermissions, RoleBasePermissionsStatus


FALSE_PERMISSIONS_FOR_TENANTADMIN = [

]

class Command(BaseCommand):
    help = f"Creates {TENANTADMIN_GROUP_NAME} Group"

    def add_arguments(self, parser):
        parser.add_argument(
            "schema_name", type=str, nargs="?", help="schema name"
        )
        return super().add_arguments(parser)
    
    def obj_created(self):

        group, created = CustomGroup.objects.get_or_create(
            name = TENANTADMIN_GROUP_NAME, level=1
        )

        all_permission_obj =    RoleBasePermissions.objects.all()
        for permission_obj in all_permission_obj:
            (
                permission,
                created
            )= RoleBasePermissionsStatus.objects.get_or_create(
                group_id=group.id, role_permission_id=permission_obj.id
            )

            permission.status = (
                False
                if permission_obj.name in FALSE_PERMISSIONS_FOR_TENANTADMIN
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
                        f"Created {TENANTADMIN_GROUP_NAME} Group for tenant {schema_name}"
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
                    f"Error in Created {TENANTADMIN_GROUP_NAME} Group :- {str(e)}"
                )
            )
