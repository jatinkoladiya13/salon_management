from rest_framework.permissions import BasePermission
from core.models import RoleBasePermissionsStatus
from django_tenants.utils import get_public_schema_name
from core.constants import TENANTADMIN_GROUP_NAME, TENANTSTAFF_GROUP_NAME

class CustomPermissionBase(BasePermission):
    permission_codename = ""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        return RoleBasePermissionsStatus.objects.filter(
            group__name=request.user.get_role,
            role_permission__name=self.permission_name,
            status=True,
        ).exists()
    

def CustomPermission(permission_name):
    return  type(
        "CustomPermission",
        (CustomPermissionBase,),
        {"permission_name":permission_name}
    )

def is_public_schema(request):
    """
    True only when the request is being served from the public schema.

    ``request.tenant`` is set by TenantMainMiddleware, but it is missing on
    requests that never reach it (websocket upgrades, some error paths), so it
    is looked up defensively instead of assumed.
    """
    tenant = getattr(request, "tenant", None)
    return tenant is not None and tenant.schema_name == get_public_schema_name()


class IsPublicSchemaSuperUser(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_authenticated:
            if request.user.is_superuser:
                if is_public_schema(request):
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
        if request.user.is_superuser and is_public_schema(request):
            return True

        # Tenant super admin
        if request.user.get_role == TENANTADMIN_GROUP_NAME:
            return True

        return False
    
class IsAdminOrStaff(BasePermission):
    """
    Allow:
    1. Public Schema Super User
    2. Tenant Super Admin
    3. Tenant Staff
    """

    def has_permission(self, request, view):

        if not request.user.is_authenticated:
            return False

        # Public schema superuser
        if request.user.is_superuser and is_public_schema(request):
            return True

        # Tenant super admin or staff
        if request.user.get_role in [TENANTADMIN_GROUP_NAME, TENANTSTAFF_GROUP_NAME]:
            return True

        return False
