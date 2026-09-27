from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework import filters

from django_filters.rest_framework import DjangoFilterBackend

from appointment.models import Services, StaffServices
from ..serializers import (
    ServiceSerializer,
    StaffServiceSerializer,
)

from utils.pagination import CustomPageNumberPagination
from utils.permissions import IsPublicSchemaSuperUser, CustomPermission
import utils.response_handler as rh

from core.constants import (
    READ_SERVICES,
    CREATE_SERVICES,
    UPDATE_SERVICES,
    DELETE_SERVICES,
    READ_STAFF_SERVICES,
    CREATE_STAFF_SERVICES,
    UPDATE_STAFF_SERVICES,
    DELETE_STAFF_SERVICES,
)


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Services.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated] 
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    pagination_class = CustomPageNumberPagination
    search_fields = ["service_name", "description"]
    filterset_fields = ["is_active", "price", "duration"]

    def get_permissions(self):
        permission_classes = [IsAuthenticated]

        schema_name = self.request.GET.get("schema_name")
        if schema_name:
            permission_classes += [IsPublicSchemaSuperUser]

        if self.action in ["list", "retrieve"]:
            permission_classes += [CustomPermission(READ_SERVICES)]

        elif self.action == "create":
            permission_classes += [CustomPermission(CREATE_SERVICES)]

        elif self.action in ["create", "update", "partial_update"]:
            permission_classes += [CustomPermission(UPDATE_SERVICES)]

        elif self.action == "destroy":
            permission_classes += [CustomPermission(DELETE_SERVICES)]

        return [permission() for permission in permission_classes]

    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Services retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = super().create(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Service created successfully"
        )
        return Response(response.response, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        serializer = super().retrieve(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Service retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        serializer = super().update(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Service updated successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data={}, error=False, msg="Service deleted successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)


class StaffServiceViewSet(viewsets.ModelViewSet):
    queryset = StaffServices.objects.all()
    serializer_class = StaffServiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    pagination_class = CustomPageNumberPagination
    search_fields = ["staff__username", "service__service_name", "service__description"]
    filterset_fields = ["staff", "service", "service__is_active", "service__price", "service__duration"]
 
    def get_permissions(self):
        permission_classes = [IsAuthenticated]

        schema_name = self.request.GET.get("schema_name")
        if schema_name:
            permission_classes += [IsPublicSchemaSuperUser]

        if self.action in ["list", "retrieve"]:
            permission_classes += [CustomPermission(READ_STAFF_SERVICES)]

        elif self.action == "create":
            permission_classes += [CustomPermission(CREATE_STAFF_SERVICES)]

        elif self.action in ["create", "update", "partial_update"]:
            permission_classes += [CustomPermission(UPDATE_STAFF_SERVICES)]

        elif self.action == "destroy":
            permission_classes += [CustomPermission(DELETE_STAFF_SERVICES)]

        return [permission() for permission in permission_classes]
    
    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Staff services retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = super().create(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Staff service created successfully"
        )
        return Response(response.response, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        serializer = super().retrieve(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Staff service retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        serializer = super().update(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Staff service updated successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data={}, error=False, msg="Staff service deleted successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)