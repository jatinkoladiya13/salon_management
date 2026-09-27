from core.constants import *
from core.constants import TENANTUSER_GROUP_NAME
from django_tenants.utils import get_tenant_model
from django.core.management.base import BaseCommand
from core.models import CustomGroup, RoleBasePermissions, RoleBasePermissionsStatus

# Permissions that are set to True for TENANTUSER_GROUP_NAME
TRUE_PERMISSIONS_FOR_TENANTUSER = [
    CREATE_OWN_ACCOUNT_ONLY,
    READ_OWN_ACCOUNT_ONLY,
    UPDATE_OWN_ACCOUNT_ONLY,

    READ_SALON_DETAILS,
    READ_SERVICES,
    READ_STAFF_SERVICES,

    READ_APPOINTMENTS,
    CREATE_APPOINTMENTS,

    READ_TIME_SLOTS,
    READ_PRODUCT_CATEGORIES,
    READ_PRODUCTS,
    READ_INVOICES,
    READ_STOCKS,
    
]

class Command(BaseCommand):
    help = f"Creates {TENANTUSER_GROUP_NAME} group"

    def add_arguments(self, parser):
        parser.add_argument(
            "schema_name", type=str, nargs="?", help="schema name"
        )
        return super().add_arguments(parser)
    
    def obj_created(self):
        group, created = CustomGroup.objects.get_or_create(
            name=TENANTUSER_GROUP_NAME, level=3
        )

        all_permissions_obj = RoleBasePermissions.objects.all()
        for permission_obj in all_permissions_obj:
            (
                permission,
                created,
            ) = RoleBasePermissionsStatus.objects.get_or_create(
                group_id=group.id, role_permission_id=permission_obj.id
            )
            permission.status = permission_obj.name in TRUE_PERMISSIONS_FOR_TENANTUSER
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
                        f"Created User Group for tenant {schema_name}"
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
                    f"Error in Created User Group :- {str(e)}"
                )
            )             
     
