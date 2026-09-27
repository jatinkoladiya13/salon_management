from django.contrib import admin
from.models import CustomGroup, RoleBasePermissions, RoleBasePermissionsStatus
# Register your models here.

@admin.register(CustomGroup)
class CustomGroupAdmin(admin.ModelAdmin):
    list_display = ["name","level"]
    search_fields =["name"]

@admin.register(RoleBasePermissions)
class RoleBasePermissionsAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]

@admin.register(RoleBasePermissionsStatus)
class RoleBasePermissionsStatusAdmin(admin.ModelAdmin):
    list_display = ["group", "role_permission", "status"]
    list_editable = ["status"]
    search_fields = ["group__name", "role_permission__name"]
    list_filter = ["group__name", "role_permission__name", "status"]
