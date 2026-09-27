from django.db import transaction
from django.utils import timezone

from rest_framework import serializers
from ..models import TimeSlot, Appointments, StaffServices
from account.serializers import UserSerializer
from .services  import ServiceSerializer


class TimeSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeSlot
        fields = "__all__"


class AppointmentSerializer(serializers.ModelSerializer):
    customer = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Appointments
        fields = "__all__"

    def validate(self, data):
        time_slot = data.get("time_slot")
        staff = data.get("staff")
        service = data.get("service")
        appointment_date = data.get("appointment_date")
        start_time = data.get("start_time")
        end_time = data.get("end_time")

        if time_slot and time_slot.is_booked:
            raise serializers.ValidationError({"time_slot": "This time slot is already booked."})

        if time_slot and staff and time_slot.staff_id != staff.id:
            raise serializers.ValidationError({"time_slot": "The selected time slot does not belong to the selected staff."})

        if time_slot and appointment_date and time_slot.slot_date != appointment_date:
            raise serializers.ValidationError({"appointment_date": "The appointment date must match the selected time slot date."})

        if time_slot and start_time and time_slot.start_time != start_time:
            raise serializers.ValidationError({"start_time": "The start time must match the selected time slot."})

        if time_slot and end_time and time_slot.end_time != end_time:
            raise serializers.ValidationError({"end_time": "The end time must match the selected time slot."})

        if service is not None and not service.is_active:
            raise serializers.ValidationError(
                {"service": "This service is no longer offered."}
            )

        # The staff member has to actually provide the service being booked.
        if staff is not None and service is not None:
            if not StaffServices.objects.filter(
                staff=staff, service=service
            ).exists():
                raise serializers.ValidationError(
                    {"staff": "This staff member does not provide the selected service."}
                )

        # Only meaningful on create; an admin closing out an old appointment
        # must still be able to edit it.
        if self.instance is None and time_slot is not None:
            slot_start = timezone.datetime.combine(
                time_slot.slot_date, time_slot.start_time
            )
            if timezone.is_naive(slot_start):
                slot_start = timezone.make_aware(
                    slot_start, timezone.get_current_timezone()
                )
            if slot_start < timezone.now():
                raise serializers.ValidationError(
                    {"time_slot": "This time slot is in the past."}
                )

        return data

    def create(self, validated_data):
        time_slot = validated_data.get("time_slot")

        with transaction.atomic():
            # Re-read the slot under a row lock. validate() checked is_booked
            # outside any transaction, so two customers submitting at the same
            # moment could both pass it and double-book the same slot.
            locked_slot = (
                TimeSlot.objects.select_for_update()
                .filter(pk=time_slot.pk)
                .first()
            )

            if locked_slot is None or locked_slot.is_booked:
                raise serializers.ValidationError(
                    {"time_slot": "This time slot is already booked."}
                )

            appointment = super().create(validated_data)

            locked_slot.is_booked = True
            locked_slot.save(update_fields=["is_booked"])

        return appointment


class AppointmentDetailSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    staff = UserSerializer(read_only=True)
    service = ServiceSerializer(read_only=True)
    time_slot = TimeSlotSerializer(read_only=True)

    class Meta:
        model = Appointments
        fields = [
            "id",
            "customer",
            "staff",
            "service",
            "time_slot",
            "notes",
            "status",
            "created_at",
            "updated_at",
        ]


class StaffAvailabilitySerializer(serializers.Serializer):
    date = serializers.DateField()
    service_id = serializers.UUIDField()