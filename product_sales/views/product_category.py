from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework import filters

from django_filters.rest_framework import DjangoFilterBackend

from product_sales.models import ProductCategory
from ..serializers import ProductCategorySerializer

from utils.pagination import CustomPageNumberPagination
from utils.permissions import IsAdmin, IsAdminOrStaff
import utils.response_handler as rh


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    pagination_class = CustomPageNumberPagination
    search_fields = ["name", "description"]
    filterset_fields = ["name", "description"]

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
            data=serializer.data, error=False, msg="Product categories retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = super().create(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Product category created successfully"
        )
        return Response(response.response, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        serializer = super().retrieve(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Product category retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        serializer = super().update(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Product category updated successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data={}, error=False, msg="Product category deleted successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)