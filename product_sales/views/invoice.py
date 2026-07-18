from rest_framework import viewsets, mixins, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from product_sales.models import Invoice
from product_sales.serializers.invoice import InvoiceSerializer
from utils.pagination import CustomPageNumberPagination
from utils.permissions import IsAdmin
import utils.response_handler as rh


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
    
    def get_permission_classes(self):
        if self.action == "destroy":
            return [IsAdmin()]
        return super().get_permission_classes()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Invoice created successfully from cart."
        )
        return Response(response.response, status=status.HTTP_201_CREATED, headers=headers)