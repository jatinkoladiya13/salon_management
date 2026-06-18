from django.shortcuts import render
from rest_framework.views import Response
from rest_framework.viewsets import ModelViewSet
from salonDetails.models import SalonDetails
from salonDetails.serializers import *
from rest_framework.permissions import IsAuthenticated
from utils.pagination import CustomPageNumberPagination
from rest_framework import filters
from rest_framework import status
from utils.permissions import CustomPermission, IsPublicSchemaSuperUser
from core.constants import *
import utils.response_handler as rh

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
        if self.request.user.is_authenticated:
            permission_classes += [IsPublicSchemaSuperUser]
 
            if self.action in ["list", "retrieve"]:
                permission_classes += [CustomPermission(READ_SALON_DETAILS)]
            elif self.action == "create":
                permission_classes += [CustomPermission(CREATE_SALON_DETAILS)]
            elif self.action in ["update", "partial_update"]:
                permission_classes += [CustomPermission(UPDATE_SALON_DETAILS)]
            elif self.action == "destroy":
                permission_classes += [CustomPermission(DELETE_SALON_DETAILS)]        

        return [permission() for permission in permission_classes]
    
    
    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)

        response = rh.ResponseMsg(
            data=serializer.data,
            error=False,
            msg="All Salon Details GET Successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)
    
    def retrieve(self, request, *args, **kwargs):
        serializer = super().retrieve(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data,
            error=False,
            msg="Salon Details Fetched Successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)
    
    def create(self, request, *args, **kwargs):
        serializer = super().create(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data,
            error=False,
            msg="Salon Details created Successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)
    
    def update(self, request, *args, **kwargs):
        serializer = super().update(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data,
            error=False,
            msg="Salon Details Updated Successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)
    
    def destroy(self, request, *args, **kwargs):
        serializer = super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data,
            error=False,
            msg="Salon Details Deleted Successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)


class SalonOpeningHoursView(ModelViewSet):
    pass

    # queryset = SalonOpeningHour.objects.all()
    # permission_classes = [IsAuthenticated]
    # serializer_class = SalonOpeningHourSerializer
    # pagination_class = CustomPageNumberPagination
    # filter_backends = [filters.SearchFilter]
    # search_fields = ["salon.name"]

    # def get_permissions(self):
    #     permission_classes = [IsAuthenticated]
    #     if self.request.user.is_authenticated:
    #         permission_classes += [IsPublicSchemaSuperUser]
 
    #         if self.action in ["list", "retrieve"]:
    #             permission_classes += [CustomPermission(READ_SALON_DETAILS)]
    #         elif self.action == "create":
    #             permission_classes += [CustomPermission(CREATE_SALON_DETAILS)]
    #         elif self.action in ["update", "partial_update"]:
    #             permission_classes += [CustomPermission(UPDATE_SALON_DETAILS)]
    #         elif self.action == "destroy":
    #             permission_classes += [CustomPermission(DELETE_SALON_DETAILS)]        

    #     return [permission() for permission in permission_classes]
    
    # def list(self, request, *args, **kwargs):
    #     serializer = super().list(request, *args, **kwargs)
    #     response = rh.ResponseMsg(
    #         serializer.data, False, "Salon Opening Hours get Successfully."
    #     )
    #     return Response(response.response, status=status.HTTP_200_OK)
    
    # def retrieve(self, request, *args, **kwargs):
    #     serializer = super().retrieve(request, *args, **kwargs)
    #     response = rh.ResponseMsg(
    #         serializer.data, False, "Salon Opening Hours fatched successfully."
    #     )
    #     return Response(response.response, status=status.HTTP_200_OK)
    
    # def create(self, request, *args, **kwargs):
    #     serializer = super().create(request, *args, **kwargs)
    #     response = rh.ResponseMsg(
    #         data=serializer.data,
    #         error=False,
    #         msg="Salon Opening Hours Created Successfully"
    #     )
    #     return Response(response.response, status=status.HTTP_200_OK)
    
    # def update(self, request, *args, **kwargs):
    #     serializer = super().update(request, *args, **kwargs)
    #     response = rh.ResponseMsg(
    #         serializer.data, False, "Salon Opening Hours Updated Successfully."
    #     )
    #     return Response(response.response, status=status.HTTP_200_OK)
    
    # def destroy(self, request, *args, **kwargs):
    #     serializer = super().destroy(request, *args, **kwargs)
    #     response = rh.ResponseMsg(
    #         serializer.data, False, "Salon Opening Hours Deleted Successfully."
    #     )
    #     return Response(response.response, status=status.HTTP_200_OK)