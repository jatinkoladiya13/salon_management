from rest_framework import serializers
from .models import *

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomGroup
        exclude = ("permissions",)

class PermissionsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleBasePermissions
        exclude = ("created_at", "updated_at")

class PermissionsStausSerializer(serializers.ModelSerializer):
    group = GroupSerializer(read_only=True)
    role_permission = PermissionsSerializer(read_only=True)

    class Meta:
        model = RoleBasePermissionsStatus
        fields = "__all__"


class PermissionsStausUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleBasePermissionsStatus
        fields = ["status"]

    def to_representation(self, instance):
        return PermissionsStausSerializer(instance).data              