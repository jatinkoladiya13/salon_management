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
from utils.permissions import IsAdmin, IsAdminOrStaff
import utils.response_handler as rh




class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Services.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [IsAuthenticated] 
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    pagination_class = CustomPageNumberPagination
    search_fields = ["service_name", "description"]
    filterset_fields = ["is_active", "price", "duration"]

    def get_permission_classes(self):
        if self.action in ["list", "retrieve"]:
            return [IsAuthenticated()]
        elif self.action in ["create", "update", "partial_update"]:
            return [IsAdminOrStaff()]
        elif self.action == "destroy":
            return [IsAdmin()]
        return super().get_permissions()

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
 
    def get_permission_classes(self):
        if self.action in ["list", "retrieve"]:
            return [IsAuthenticated()]
        elif self.action in ["create", "update", "partial_update"]:
            return [IsAdminOrStaff()]
        elif self.action == "destroy":
            return [IsAdmin()]
        return super().get_permissions()

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