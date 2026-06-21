from rest_framework.permissions import BasePermission
from core.models import RoleBasePermissionsStatus
from django_tenants.utils import get_public_schema_name
from core.constants import TENANTADMIN_GROUP_NAME

class CustomPermissionBase(BasePermission):
    permission_codename = ""

    def has_permission(self, request, view):
        print("-----------:-", self.permission_name, request.user)
        obj = RoleBasePermissionsStatus.objects.filter(
            group__name=request.user.get_role,
            role_permission__name=self.permission_name,
            status=True,
        ).exists()
        print("************:-", obj, self.permission_name, request.user)
        return obj
    

def CustomPermission(permission_name):
    return  type(
        "CustomPermission",
        (CustomPermissionBase,),
        {"permission_name":permission_name}
    )

class IsPublicSchemaSuperUser(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_authenticated:
            if request.user.is_superuser:
                if request.tenant.schema_name == get_public_schema_name():
                    return True

        return False

class IsTenantSuperAdmin(BasePermission):
    def has_permission(self, request, view):

        if request.user.is_authenticated:
            if request.user.get_role == TENANTADMIN_GROUP_NAME:
                return True
        return False    


class IsAdmin(BasePermission):
    """
    Allow:
    1. Public Schema Super User
    2. Tenant Super Admin
    """

    def has_permission(self, request, view):

        if not request.user.is_authenticated:
            return False

        # Public schema superuser
        if (
            request.user.is_superuser
            and request.tenant.schema_name == get_public_schema_name()
        ):
            return True

        # Tenant super admin
        if request.user.get_role == TENANTADMIN_GROUP_NAME:
            return True

        return False