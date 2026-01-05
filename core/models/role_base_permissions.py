from django.db import models
from salon_management.behaviours import DateMixin
from django.utils.translation import gettext_lazy as _

class RoleBasePermissions(DateMixin):
    name = models.CharField(
        verbose_name=_("Name"), max_length=100, unique=True
    )
    description = models.TextField(
        verbose_name=_("Text"), blank=True, null=True, default=None
    )

    class Meta:
        db_table = "role_base_permissions"
        verbose_name = "role_base_permission"
        verbose_name_plural = "role_base_permissions"
        indexes = [models.Index(fields=["name"])]
        ordering = ("-created_at",)

    def __str__(self):
        return self.name    