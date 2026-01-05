from rest_framework.mixins import ListModelMixin, CreateModelMixin, UpdateModelMixin, DestroyModelMixin
from rest_framework.viewsets import GenericViewSet
from core.serializers import *
from rest_framework.permissions import IsAuthenticated
from utils.pagination import CustomPageNumberPagination
from rest_framework import filters
from rest_framework.response import Response
import utils.response_handler as rh
from rest_framework import status
from utils.permissions import CustomPermission, IsPublicSchemaSuperUser
from .models import RoleBasePermissionsStatus, CustomGroup
from django_tenants.utils import schema_context
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from core.constants import (
    READ_GROUPS,
    CREATE_GROUPS,
    UPDATE_GROUPS,
    DELETE_GROUPS,
    READ_PERMISSIONS_STATUS,
    UPDATE_PERMISSIONS_STATUS,
    SUPERADMIN_GROUP_NAME,
)


# Create your views here.

class Groupview(ListModelMixin, CreateModelMixin, UpdateModelMixin, DestroyModelMixin, GenericViewSet):
    queryset = CustomGroup.objects.all()
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]

    def get_permission(self):
        permission_classes  = [IsAuthenticated]
        if self.request.user.is_authenticated:
            schema_name  =self.request.GET.get("schema_name")
            if schema_name:
                permission_classes += [IsPublicSchemaSuperUser]

            if self.action == "list":
                permission_classes += [CustomPermission(READ_GROUPS)]
            elif self.action == "create":
                permission_classes += [CustomPermission(CREATE_GROUPS)]
            elif self.action  in ["update", "partial_update"]:
                permission_classes += [CustomPermission(UPDATE_GROUPS)]
            elif self.action == "destroy":
                permission_classes += [CustomPermission(DELETE_GROUPS)]    

        return [permission() for permission in permission_classes]

    def list(self, request, *args,  **kwargs):
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                serializer_data = super().list(request, *args, **kwargs)
        else:
            serializer_data =  super().list(request, *args, **kwargs)

        response = rh.ResponseMsg(
            data=serializer_data.data,
            error=False,
            msg="All Groups Get Successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)
    
    def create(self, request, *args, **kwargs):
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                serializer_data = super().create(request, *args, **kwargs)
        else:
            serializer_data = super().create(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer_data.data,
            error=False,
            msg="Group Create Successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)
    
    def update(self, request, *args, **kwargs):
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                instance = self.get_object()
                if instance.name == SUPERADMIN_GROUP_NAME:
                    raise Exception("You Can't Update this role!!!")
                serializer_data = super().update(request, *args, **kwargs)
        else:
            instance = self.get_object()
            if instance.name == SUPERADMIN_GROUP_NAME:
                raise Exception("You Can't Update this role!!!")
            serializer_data = super().update(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer_data.data,
            error=False,
            msg="Group update Successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                instance = self.get_object()
                if instance.name == SUPERADMIN_GROUP_NAME:
                    raise Exception("You Can't delete this role!!!")
                super().destroy(request, *args, **kwargs)
        else:
            instance = self.get_object()
            if instance.name == SUPERADMIN_GROUP_NAME:
                raise Exception("You Can't delete this role!!!")
            super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data={}, error=False, msg="Group delete Successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)   
    
class PermissionStatusView(ListModelMixin, UpdateModelMixin, GenericViewSet):
    queryset = RoleBasePermissionsStatus.objects.all()
    serializer_class = PermissionsStausSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ["group__name", "role_permission__name", "status"]
    filterset_fields = {"group__id":["exact"]}

    def get_permissions(self):
        permission_classes = [IsAuthenticated]
        if self.request.user.is_authenticated:
            schema_name = self.request.GET.get("schema_name")
            if schema_name:
                permission_classes += [IsPublicSchemaSuperUser]
           
            elif self.action == "list":
                permission_classes += [
                    CustomPermission(READ_PERMISSIONS_STATUS)
                ]
            elif self.action in ["update", "partial_update"]:
                permission_classes += [
                    CustomPermission(UPDATE_PERMISSIONS_STATUS)
                ]    

        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action == "update":
            self.serializer_class = PermissionsStausUpdateSerializer
        return super().get_serializer_class()
    
    def list(self, request, *args, **kwargs):
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                serializer_data = super().list(request, *args, **kwargs)
        else:
            serializer_data = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer_data.data,
            error=False,
            msg="All Permissions with Role GET Successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)
    
    def update(self, request, *args, **kwargs):
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                instance  = self.get_object()
                if instance.group.name == SUPERADMIN_GROUP_NAME:
                    raise Exception(
                        "You Can't update permission for this role!!!"
                    )
                serializer_data = super().update(request, *args, **kwargs)
        else:
            instance = self.get_object()
            if instance.group.name == SUPERADMIN_GROUP_NAME:
                raise Exception("You Can't update permission for this role!!!")
            serializer_data = super().update(request, *args, **kwargs)
       
        response = rh.ResponseMsg(
            data=serializer_data.data,
            error=False,
            msg="Update permission status for role Successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def validate_data(self, data, schema_name):
        for permission_data in data:
            try:
                if schema_name:
                    with schema_context(schema_name):
                        obj = RoleBasePermissionsStatus.objects.get(
                            id=permission_data["id"]
                        )
                        if obj.group.name == SUPERADMIN_GROUP_NAME:
                            raise Exception(
                                "You Can't update permission for this role!!!"
                            )
                else:
                    obj = RoleBasePermissionsStatus.objects.get(
                        id=permission_data["id"]
                    )
                    if obj.group.name == SUPERADMIN_GROUP_NAME:
                        raise Exception(
                            "You Can't update permission for this role!!!"
                        )
            except RoleBasePermissionsStatus.DoesNotExist:
                raise NotFound(
                    "All permissions Doesn't exist in database, Please check!!!"
                )
        return True    
    
    @action(
        methods=["PUT"],
        permission_classes=[CustomPermission(UPDATE_PERMISSIONS_STATUS)],
        detail=False,
    )
    def update_bulk_permissions(self, request):
        data = request.data.get("data", None)
        schema_name = request.GET.get("schema_name", None)
        if not data:
            raise NotFound("please, pass all permissions data!!!")
        self.validate_data(data=data, schema_name=schema_name)
        instances = []
        for permission_data in data:
            try:
                if schema_name:
                    with schema_context(schema_name):
                        obj = RoleBasePermissionsStatus.objects.get(
                            id=permission_data["id"]
                        )
                        obj.status = permission_data["status"]
                        obj.save()
                        instances.append(obj)
                else:
                    obj = RoleBasePermissionsStatus.objects.get(
                        id=permission_data["id"]
                    )
                    obj.status = permission_data["status"]
                    obj.save()
                    instances.append(obj)

            except RoleBasePermissionsStatus.DoesNotExist:
                raise NotFound(
                    "All permissions Doesn't exist in database, Please check!!!"
                )

        serializer = PermissionsStausSerializer(instances, many=True)
        response = rh.ResponseMsg(
            serializer.data,
            False,
            "Update all the Permissions Successfully!!!",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
