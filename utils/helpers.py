from core.models import RoleBasePermissionsStatus

def is_permission(role, permission_name):
    obj = RoleBasePermissionsStatus.objects.filter(
        group__name = role, role_permission__name=permission_name, status=True
    ).exists()

    return obj

