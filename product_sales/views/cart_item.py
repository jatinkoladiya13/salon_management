from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework import filters

from django_filters.rest_framework import DjangoFilterBackend

from ..serializers import CartItemSerializer
from ..models import CartItem

from utils.pagination import CustomPageNumberPagination
from utils.permissions import IsAdmin, IsAdminOrStaff
import utils.response_handler as rh


class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    pagination_class = CustomPageNumberPagination
    search_fields = ["product__name", "product__description"]
    filterset_fields = ["product__name", "quantity"]

    def get_queryset(self):
        """
        This view should return a list of all the cart items
        for the currently authenticated user.
        """
        return CartItem.objects.filter(user=self.request.user)

    def get_permissions(self):
        # Every action here is already scoped to the requesting user's own cart
        # by get_queryset(), so owning the row is the authorisation - a customer
        # has to be able to remove their own item.
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Cart items retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = super().create(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Cart item created successfully"
        )
        return Response(response.response, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        serializer = super().retrieve(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Cart item retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        serializer = super().update(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Cart item updated successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data={}, error=False, msg="Cart item deleted successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)