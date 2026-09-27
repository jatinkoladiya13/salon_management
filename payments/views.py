from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import PaymentConfiguration
from .serializers import PaymentConfigurationSerializer
import utils.response_handler as rh
from utils.permissions import IsAdmin

# Create your views here.

class PaymentConfigurationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Payment Configurations.
    """
    queryset = PaymentConfiguration.objects.all()
    serializer_class = PaymentConfigurationSerializer
    permission_classes = [IsAdmin]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response_data = rh.ResponseMsg(
            data=response.data, error=False, msg="Payment configurations retrieved successfully"
        )
        return Response(response_data.response, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response_data = rh.ResponseMsg(
            data=response.data, error=False, msg="Payment configuration created successfully"
        )
        return Response(response_data.response, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        response_data = rh.ResponseMsg(
            data=response.data, error=False, msg="Payment configuration retrieved successfully"
        )
        return Response(response_data.response, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        response_data = rh.ResponseMsg(
            data=response.data, error=False, msg="Payment configuration updated successfully"
        )
        return Response(response_data.response, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        response_data = rh.ResponseMsg(data={}, error=False, msg="Payment configuration deleted successfully")
        return Response(response_data.response, status=status.HTTP_200_OK)
