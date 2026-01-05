from django.db import models
from .group import CustomGroup
from .role_base_permissions import RoleBasePermissions
from django.utils.translation import gettext_lazy  as _
from salon_management.behaviours import DateMixin


class RoleBasePermissionsStatus(DateMixin):
    group = models.ForeignKey(
        CustomGroup, verbose_name=_("Group"), on_delete=models.CASCADE
    )
    role_permission = models.ForeignKey(
        RoleBasePermissions,
        verbose_name=_("Role Permission"),
        on_delete=models.CASCADE
    )
    status = models.BooleanField(default=False)

    class Meta:
        unique_together = (
            "group",
            "role_permission",
        )
        db_table = "role_base_permissions_status"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["group", "role_permission"])]

    def __str__(self) -> str:
        return (
            str(self.group.name)
            + " | "
            + str(self.role_permission.name)
            + " | "
            + str(self.status)
        )
    