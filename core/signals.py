from django.db.models.signals import post_save
from django.dispatch import receiver
from core.models import  CustomGroup
from .models import RoleBasePermissions, RoleBasePermissionsStatus

@receiver(post_save, sender=CustomGroup)
def handle_group_save(sender, instance, created, **kwargs):
    """
    Signal handler for post_save signal on Group model.
    """
    if created:
        all_permission_obj = RoleBasePermissions.objects.all()
        for permission_obj in all_permission_obj:
            RoleBasePermissionsStatus.objects.get_or_create(
                group_id = instance.id, role_permission_id=permission_obj.id
            )