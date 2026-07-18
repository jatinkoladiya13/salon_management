from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import render

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework import filters

from utils.pagination import CustomPageNumberPagination
from utils.permissions import IsAdmin, IsAdminOrStaff
import utils.response_handler as rh

from .models import StockPurchase
from .serializers import StockPurchaseSerializer

# Create your views here.
class StockPurchaseViewSet(viewsets.ModelViewSet):
    queryset = (
        StockPurchase.objects
        .prefetch_related(
            "items",
            "items__product",
        )
        .all()
    )
    serializer_class = StockPurchaseSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend,filters.SearchFilter,filters.OrderingFilter,]
    filterset_fields = ["payment_status","purchase_date",]
    search_fields = ["invoice_number",]
    ordering_fields = ["purchase_date","total_amount",]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [IsAuthenticated]
        elif self.action in ["create", "update", "partial_update"]:
            permission_classes = [IsAdminOrStaff]
        elif self.action == "destroy":
            permission_classes = [IsAdmin]
        else:
            permission_classes = self.permission_classes

        return [permission() for permission in permission_classes]

    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Stock purchase retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)
    
    def retrieve(self, request, *args, **kwargs):
        serializer = super().retrieve(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Stock purchase retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Stock purchase created successfully."
        )
        return Response(response.response, status=status.HTTP_200_OK)


    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Stock purchase updated successfully."
        )
        return Response(response.response, status=status.HTTP_200_OK)
            
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)

        response = rh.ResponseMsg(
            data=None, error=False, msg="Stock purchase deleted successfully."
        )
        return Response(response.response, status=status.HTTP_200_OK)
    