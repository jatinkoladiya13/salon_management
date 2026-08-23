from rest_framework import viewsets, mixins, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from product_sales.models import Invoice
from product_sales.serializers.invoice import InvoiceSerializer
from utils.pagination import CustomPageNumberPagination
from utils.permissions import IsPublicSchemaSuperUser, CustomPermission
import utils.response_handler as rh

from core.constants import (
    READ_INVOICES,
    CREATE_INVOICES,
    UPDATE_INVOICES,
    DELETE_INVOICES,

)

class InvoiceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet for creating and listing invoices.
    """

    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        """
        This view should return a list of all the invoices
        for the currently authenticated user.
        """
        return Invoice.objects.filter(user=self.request.user)
    
    def get_permissions(self):
        permission_classes = [IsAuthenticated]

        schema_name = self.request.GET.get("schema_name")
        if schema_name:
            permission_classes += [IsPublicSchemaSuperUser]

        if self.action in ["list", "retrieve"]:
            permission_classes += [CustomPermission(READ_INVOICES)]

        elif self.action == "create":
            permission_classes += [CustomPermission(CREATE_INVOICES)]

        elif self.action in ["create", "update", "partial_update"]:
            permission_classes += [CustomPermission(UPDATE_INVOICES)]

        elif self.action == "destroy":
            permission_classes += [CustomPermission(DELETE_INVOICES)]

        return [permission() for permission in permission_classes]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Invoice created successfully from cart."
        )
        return Response(response.response, status=status.HTTP_201_CREATED, headers=headers)