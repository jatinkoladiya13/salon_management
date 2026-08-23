from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework import filters

from django_filters.rest_framework import DjangoFilterBackend

from product_sales.models import Product
from ..serializers import ProductSerializer

from utils.pagination import CustomPageNumberPagination
from utils.permissions import IsPublicSchemaSuperUser, CustomPermission
import utils.response_handler as rh

from core.constants import (
    READ_PRODUCTS,
    CREATE_PRODUCTS,
    UPDATE_PRODUCTS,
    DELETE_PRODUCTS,
)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    pagination_class = CustomPageNumberPagination
    search_fields = ["name", "description"]
    filterset_fields = ["name", "description", "selling_price", "product_category", "is_active"]

    def get_permissions(self):
        permission_classes = [IsAuthenticated]

        schema_name = self.request.GET.get("schema_name")
        if schema_name:
            permission_classes += [IsPublicSchemaSuperUser]

        if self.action in ["list", "retrieve"]:
            permission_classes += [CustomPermission(READ_PRODUCTS)]

        elif self.action == "create":
            permission_classes += [CustomPermission(CREATE_PRODUCTS)]

        elif self.action in ["create", "update", "partial_update"]:
            permission_classes += [CustomPermission(UPDATE_PRODUCTS)]

        elif self.action == "destroy":
            permission_classes += [CustomPermission(DELETE_PRODUCTS)]

        return [permission() for permission in permission_classes]

    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Products retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = super().create(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Product created successfully"
        )
        return Response(response.response, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        serializer = super().retrieve(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Product retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        serializer = super().update(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Product updated successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data={}, error=False, msg="Product deleted successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)