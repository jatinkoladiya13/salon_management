from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import viewsets, status
from rest_framework import filters

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
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
from utils.permissions import IsAdmin, IsAdminOrStaff, IsPublicSchemaSuperUser, CustomPermission
import utils.response_handler as rh

from core.constants import (
    READ_APPOINTMENTS,
    CREATE_APPOINTMENTS,
    UPDATE_APPOINTMENTS,
    DELETE_APPOINTMENTS,
    READ_TIME_SLOTS,
    CREATE_TIME_SLOTS,
    UPDATE_TIME_SLOTS,
    DELETE_TIME_SLOTS,
)

class TimeSlotViewSet(viewsets.ModelViewSet):
    queryset = TimeSlot.objects.all()
    serializer_class = TimeSlotSerializer
    permission_classes = [IsAuthenticated] 
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    pagination_class = CustomPageNumberPagination
    search_fields = ["staff__username", "staff__email", "slot_date"]
    filterset_fields = ["staff", "slot_date", "is_booked","start_time", "end_time"]

    def get_permissions(self):
        permission_classes = [IsAuthenticated]

        schema_name = self.request.GET.get("schema_name")
        if schema_name:
            permission_classes += [IsPublicSchemaSuperUser]

        if self.action in ["list", "retrieve"]:
            permission_classes += [CustomPermission(READ_TIME_SLOTS)]

        elif self.action == "create":
            permission_classes += [CustomPermission(CREATE_TIME_SLOTS)]

        elif self.action in ["create", "update", "partial_update"]:
            permission_classes += [CustomPermission(UPDATE_TIME_SLOTS)]

        elif self.action == "destroy":
            permission_classes += [CustomPermission(DELETE_TIME_SLOTS)]

        return [permission() for permission in permission_classes]
    

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

    def get_permissions(self):
        permission_classes = [IsAuthenticated]

        schema_name = self.request.GET.get("schema_name")
        if schema_name:
            permission_classes += [IsPublicSchemaSuperUser]

        if self.action in ["list", "retrieve"]:
            permission_classes += [CustomPermission(READ_APPOINTMENTS)]

        elif self.action == "create":
            permission_classes += [CustomPermission(CREATE_APPOINTMENTS)]

        elif self.action in ["update", "partial_update"]:
            permission_classes += [IsAdminOrStaff, CustomPermission(UPDATE_APPOINTMENTS)]

        elif self.action == "destroy":
            permission_classes += [IsAdmin, CustomPermission(DELETE_APPOINTMENTS)]

        return [permission() for permission in permission_classes]

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
        # The slot lock, the "already booked" check and flipping is_booked all
        # live in AppointmentSerializer.create() so they happen inside one
        # transaction. This used to reference rh.MyCustomException, which does
        # not exist - the moment two customers raced for a slot the loser got
        # an AttributeError instead of a validation error.
        user = self.request.user
        role = user.get_role

        if role == TENANTADMIN_GROUP_NAME or role == TENANTSTAFF_GROUP_NAME:
            serializer.save()  # Admin/Staff can specify the customer in the request
        else:
            serializer.save(customer=user)  # Customer is booking for themselves

    def perform_update(self, serializer):
        appointment = serializer.save()

        # Cancelling or marking a no-show has to hand the slot back, otherwise
        # it stays flagged as booked and can never be sold again.
        time_slot = appointment.time_slot
        if time_slot is not None:
            should_be_booked = appointment.status not in ("cancelled", "no_show")
            if time_slot.is_booked != should_be_booked:
                time_slot.is_booked = should_be_booked
                time_slot.save(update_fields=["is_booked"])

    def perform_destroy(self, instance):
        time_slot = instance.time_slot
        with transaction.atomic():
            instance.delete()
            # time_slot is PROTECT, so the slot outlives the appointment and
            # would otherwise stay permanently unbookable.
            if time_slot is not None and time_slot.is_booked:
                time_slot.is_booked = False
                time_slot.save(update_fields=["is_booked"])

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

    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        status_summary = (
            queryset.values("status")
            .annotate(count=Count("id"))
            .order_by("status")
        )

        counts = {
            "pending": 0,
            "confirmed": 0,
            "in_progress": 0,
            "completed": 0,
            "cancelled": 0,
            "no_show": 0,
        }
        for item in status_summary:
            status_name = item.get("status")
            if status_name in counts:
                counts[status_name] = item.get("count", 0)

        payload = {
            "summary": {
                "total_appointments": queryset.count(),
                "pending_appointments": counts["pending"],
                "confirmed_appointments": counts["confirmed"],
                "in_progress_appointments": counts["in_progress"],
                "completed_appointments": counts["completed"],
                "cancelled_appointments": counts["cancelled"],
                "no_show_appointments": counts["no_show"],
                "active_services": Services.objects.filter(is_active=True).count(),
            }
        }

        response = rh.ResponseMsg(
            data=payload,
            error=False,
            msg="Dashboard summary retrieved successfully",
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

        # Find staff who provide the service. Deactivated staff must not be
        # offered for booking.
        staff_providing_service = StaffServices.objects.filter(
            service=service, staff__is_active=True
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

        # Avoid showing past slots. localtime(), not datetime.now(): USE_TZ is
        # on, so the naive local clock could hide or expose the wrong slots.
        now = timezone.localtime()
        if date < now.date():
            available_slots = available_slots.none()
        elif date == now.date():
            available_slots = available_slots.filter(start_time__gte=now.time())

        slot_serializer = TimeSlotSerializer(available_slots, many=True)
        response = rh.ResponseMsg(
            data=slot_serializer.data, error=False, msg="Available slots retrieved"
        )
        return Response(response.response, status=status.HTTP_200_OK)
