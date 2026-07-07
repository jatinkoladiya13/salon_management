from rest_framework import serializers
from ..models import TimeSlot, Appointments
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

        return data

    def create(self, validated_data):
        appointment = super().create(validated_data)
        time_slot = appointment.time_slot
        time_slot.is_booked = True
        time_slot.save()
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