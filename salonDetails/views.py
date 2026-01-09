from django.shortcuts import render
from rest_framework.views import Response
from rest_framework.viewsets import ModelViewSet
from salonDetails.models import SalonDetails 
from salonDetails.serializers import SalonDetailsSerializer, SalonDetailsCreateSerializer, SalongDetailsRetrieveSerializer
from rest_framework.permissions import IsAuthenticated
from utils.pagination import CustomPageNumberPagination
from rest_framework import filters
# Create your views here.

class SalonDetailView(ModelViewSet):
    queryset = SalonDetails.objects.all()
    serializer_class = SalonDetailsSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            self.serializer_class = SalonDetailsCreateSerializer
        elif self.action in ["retrieve"]:
            self.serializer_class = SalongDetailsRetrieveSerializer
        return super().get_serializer_class()
    
    def get_permissions(self):
        permission_classes = [IsAuthenticated]
        return super().get_permissions()

   
