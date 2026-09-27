"""
Shared test scaffolding.

Most of this project's models live in the tenant schemas, so a plain
``django.test.TestCase`` runs against the public schema where those tables do
not exist. Everything that touches a tenant app must therefore build on
``TenantAPITestCase`` below.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command

from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context

from rest_framework.test import APIClient

from core.constants import (
    CREATE_APPOINTMENTS,
    CREATE_INVOICES,
    CREATE_PRODUCTS,
    CREATE_PRODUCT_CATEGORIES,
    CREATE_SERVICES,
    CREATE_STAFF_SERVICES,
    CREATE_STOCKS,
    CREATE_TIME_SLOTS,
    DELETE_APPOINTMENTS,
    DELETE_INVOICES,
    DELETE_PRODUCTS,
    DELETE_PRODUCT_CATEGORIES,
    DELETE_SERVICES,
    DELETE_STAFF_SERVICES,
    DELETE_STOCKS,
    DELETE_TIME_SLOTS,
    READ_APPOINTMENTS,
    READ_INVOICES,
    READ_PRODUCTS,
    READ_PRODUCT_CATEGORIES,
    READ_SERVICES,
    READ_STAFF_SERVICES,
    READ_STOCKS,
    READ_TIME_SLOTS,
    TENANTADMIN_GROUP_NAME,
    TENANTSTAFF_GROUP_NAME,
    TENANTUSER_GROUP_NAME,
    UPDATE_APPOINTMENTS,
    UPDATE_INVOICES,
    UPDATE_PRODUCTS,
    UPDATE_PRODUCT_CATEGORIES,
    UPDATE_SERVICES,
    UPDATE_STAFF_SERVICES,
    UPDATE_STOCKS,
    UPDATE_TIME_SLOTS,
)
from core.models import CustomGroup, RoleBasePermissions, RoleBasePermissionsStatus

User = get_user_model()


class TenantAPITestCase(TenantTestCase):
    """
    A migrated tenant schema plus the three tenant roles and one user each.

    Subclasses get ``self.admin`` (TenantAdmin), ``self.staff`` (Staff) and
    ``self.customer`` (User), and an ``APIClient`` already pointed at the
    tenant's host.
    """

    HOST = "test.localhost"
    PASSWORD = "Password@123"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain.domain = cls.HOST
        cls.domain.save()

        cls.tenant.create_schema(check_if_exists=True, verbosity=0)
        call_command(
            "migrate_schemas",
            schema_name=cls.tenant.schema_name,
            interactive=False,
            verbosity=0,
        )

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.defaults["HTTP_HOST"] = self.HOST

        with schema_context(self.tenant.schema_name):
            CustomGroup.objects.all().delete()

            # Let the database assign the primary keys. CustomGroup is a
            # multi-table child of auth.Group, so hardcoding ids here leaves the
            # shared auth_group sequence behind and the next group created
            # through the API collides with one of them.
            self.admin_group = CustomGroup.objects.create(
                name=TENANTADMIN_GROUP_NAME, level=1
            )
            self.staff_group = CustomGroup.objects.create(
                name=TENANTSTAFF_GROUP_NAME, level=2
            )
            self.user_group = CustomGroup.objects.create(
                name=TENANTUSER_GROUP_NAME, level=3
            )
            self.seed_default_permissions()

            self.admin = User.objects.create_user(
                email="admin@tenant.test",
                password=self.PASSWORD,
                first_name="Admin",
                last_name="User",
                is_active=True,
                groups=[self.admin_group],
            )
            self.staff = User.objects.create_user(
                email="staff@tenant.test",
                password=self.PASSWORD,
                first_name="Staff",
                last_name="Member",
                is_active=True,
                groups=[self.staff_group],
            )
            self.customer = User.objects.create_user(
                email="customer@tenant.test",
                password=self.PASSWORD,
                first_name="Customer",
                last_name="User",
                is_active=True,
                groups=[self.user_group],
            )

    def seed_default_permissions(self):
        """Mirror the project group bootstrap so role-based checks work in tests."""
        with schema_context(self.tenant.schema_name):
            # Keep the test role matrix aligned with every permission checked
            # by the tenant APIs, including product-sales endpoints.
            permission_names = {
                READ_SERVICES,
                CREATE_SERVICES,
                UPDATE_SERVICES,
                DELETE_SERVICES,
                READ_STAFF_SERVICES,
                CREATE_STAFF_SERVICES,
                UPDATE_STAFF_SERVICES,
                DELETE_STAFF_SERVICES,
                READ_APPOINTMENTS,
                CREATE_APPOINTMENTS,
                UPDATE_APPOINTMENTS,
                DELETE_APPOINTMENTS,
                READ_TIME_SLOTS,
                CREATE_TIME_SLOTS,
                UPDATE_TIME_SLOTS,
                DELETE_TIME_SLOTS,
                READ_PRODUCT_CATEGORIES,
                CREATE_PRODUCT_CATEGORIES,
                UPDATE_PRODUCT_CATEGORIES,
                DELETE_PRODUCT_CATEGORIES,
                READ_PRODUCTS,
                CREATE_PRODUCTS,
                UPDATE_PRODUCTS,
                DELETE_PRODUCTS,
                READ_INVOICES,
                CREATE_INVOICES,
                UPDATE_INVOICES,
                DELETE_INVOICES,
                READ_STOCKS,
                CREATE_STOCKS,
                UPDATE_STOCKS,
                DELETE_STOCKS,
            }
            for permission_name in permission_names:
                RoleBasePermissions.objects.get_or_create(name=permission_name)
            all_permissions = list(RoleBasePermissions.objects.all())

            permission_by_name = {permission.name: permission for permission in all_permissions}

            for group in (self.admin_group, self.staff_group, self.user_group):
                for permission in all_permissions:
                    row, _ = RoleBasePermissionsStatus.objects.get_or_create(
                        group=group,
                        role_permission=permission,
                    )
                    if group.name == TENANTADMIN_GROUP_NAME:
                        row.status = True
                    elif group.name == TENANTSTAFF_GROUP_NAME:
                        row.status = permission.name not in {
                            DELETE_SERVICES,
                            DELETE_STAFF_SERVICES,
                            DELETE_APPOINTMENTS,
                            DELETE_TIME_SLOTS,
                            DELETE_PRODUCT_CATEGORIES,
                            DELETE_PRODUCTS,
                            DELETE_INVOICES,
                            DELETE_STOCKS,
                        }
                    elif group.name == TENANTUSER_GROUP_NAME:
                        row.status = permission.name in {
                            READ_SERVICES,
                            READ_STAFF_SERVICES,
                            READ_APPOINTMENTS,
                            CREATE_APPOINTMENTS,
                            READ_TIME_SLOTS,
                            READ_PRODUCT_CATEGORIES,
                            READ_PRODUCTS,
                            READ_INVOICES,
                            CREATE_INVOICES,
                            READ_STOCKS,
                        }
                    row.save(update_fields=["status"])

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def grant(self, group, permission_name, status=True):
        """Switch a single role-based permission on (or off) for a group."""
        with schema_context(self.tenant.schema_name):
            permission, _ = RoleBasePermissions.objects.get_or_create(
                name=permission_name
            )
            row, _ = RoleBasePermissionsStatus.objects.get_or_create(
                group=group, role_permission=permission
            )
            row.status = status
            row.save(update_fields=["status"])
            return row


def get_or_create_public_tenant():
    """
    The public tenant row, created on demand.

    ``TenantTestCase`` only builds the one test tenant, but the tenant and
    subscription-admin APIs are gated on being served from the public schema.
    """
    from tenant.models import Domain, Tenant

    public_schema = get_public_schema_name()

    with schema_context(public_schema):
        tenant, _ = Tenant.objects.get_or_create(
            schema_name=public_schema,
            defaults={"name": "public"},
        )
        Domain.objects.get_or_create(
            domain="public.localhost",
            defaults={"tenant": tenant, "is_primary": False},
        )

    return tenant
