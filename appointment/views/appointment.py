from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import viewsets, status
from rest_framework import filters

from django_filters.rest_framework import DjangoFilterBackend

from ..models import Services, StaffServices, TimeSlot, Appointments
from ..serializers import (
    TimeSlotSerializer,
    AppointmentSerializer,
    AppointmentDetailSerializer,
    StaffAvailabilitySerializer,
)

# from .permissions import IsAdminOrStaff, IsOwnerOrAdminOrStaff
from core.constants import TENANTADMIN_GROUP_NAME, TENANTSTAFF_GROUP_NAME
from datetime import datetime

from utils.pagination import CustomPageNumberPagination
from utils.permissions import IsAdmin, IsAdminOrStaff
import utils.response_handler as rh



class TimeSlotViewSet(viewsets.ModelViewSet):
    queryset = TimeSlot.objects.all()
    serializer_class = TimeSlotSerializer
    permission_classes = [IsAuthenticated] 
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    pagination_class = CustomPageNumberPagination
    search_fields = ["staff__username", "staff__email", "slot_date"]
    filterset_fields = ["staff", "slot_date", "is_booked","start_time", "end_time"]

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
            data=serializer.data, error=False, msg="Time slots retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = super().create(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Time slot created successfully"
        )
        return Response(response.response, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        serializer = super().retrieve(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Time slot retrieved successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        serializer = super().update(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Time slot updated successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data={}, error=False, msg="Time slot deleted successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)


class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointments.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    pagination_class = CustomPageNumberPagination
    search_fields = ["customer__username", "customer__email", "staff__username", "staff__email", "service__service_name"]
    filterset_fields = ["customer", "staff", "service", "time_slot__slot_date", "status"]

    def get_permission_classes(self):
        if self.action in ["list", "retrieve"]:
            return [IsAuthenticated()]
        elif self.action == "create":
            return [IsAuthenticated()]
        elif self.action in ["update", "partial_update"]:
            return [IsAdminOrStaff()]
        elif self.action == "destroy":
            return [IsAdmin()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == "available_slots":
            return StaffAvailabilitySerializer
        if self.action in ["list", "retrieve"]:
            return AppointmentDetailSerializer
        return AppointmentSerializer

    def get_queryset(self):
        user = self.request.user
        role = user.get_role

        if role == TENANTADMIN_GROUP_NAME:
            return Appointments.objects.all()  # Admin can see all appointments
        if role == TENANTSTAFF_GROUP_NAME:
            return Appointments.objects.filter(staff=user)  # Staff see their appointments
        return Appointments.objects.filter(customer=user)

    def perform_create(self, serializer):
        time_slot = serializer.validated_data.get("time_slot")
        if time_slot and time_slot.is_booked:
            raise rh.MyCustomException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message={"time_slot": ["This time slot is already booked."]},
                error=True,
            )


        user = self.request.user
        role = user.get_role

        if role == TENANTADMIN_GROUP_NAME or role == TENANTSTAFF_GROUP_NAME:
            serializer.save()  # Admin/Staff can specify the customer in the request
        else:
            serializer.save(customer=user) # Customer is booking for themselves

        if time_slot:
            time_slot.is_booked = True
            time_slot.save()

    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data,
            error=False,
            msg="Appointments retrieved successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = super().create(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Appointment created successfully"
        )
        return Response(response.response, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        serializer = super().retrieve(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data,
            error=False,
            msg="Appointment retrieved successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        serializer = super().update(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data=serializer.data, error=False, msg="Appointment updated successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg(
            data={}, error=False, msg="Appointment deleted successfully"
        )
        return Response(response.response, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], serializer_class=StaffAvailabilitySerializer)
    def available_slots(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        date = serializer.validated_data["date"]
        service_id = serializer.validated_data["service_id"]

        try:
            service = Services.objects.get(id=service_id)
        except Services.DoesNotExist:
            response = rh.ResponseMsg(data={}, error=True, msg="Service not found")
            return Response(response.response, status=status.HTTP_404_NOT_FOUND)

        # Find staff who provide the service
        staff_providing_service = StaffServices.objects.filter(
            service=service
        ).values_list("staff", flat=True)

        if not staff_providing_service:
            response = rh.ResponseMsg(
                data=[], error=False, msg="No staff available for this service."
            )
            return Response(response.response, status=status.HTTP_200_OK)

        # Find available time slots for these staff on the given date
        available_slots = TimeSlot.objects.filter(
            staff_id__in=staff_providing_service,
            slot_date=date,
            is_booked=False,
        )

        # Avoid showing past slots
        now = datetime.now().time()
        if date == datetime.now().date():
            available_slots = available_slots.filter(start_time__gte=now)

        slot_serializer = TimeSlotSerializer(available_slots, many=True)
        response = rh.ResponseMsg(
            data=slot_serializer.data, error=False, msg="Available slots retrieved"
        )
        return Response(response.response, status=status.HTTP_200_OK)
