

from rest_framework import serializers
from ..models import Services, StaffServices
from decimal import Decimal

class ServiceSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)
    duration = serializers.IntegerField(required=True, min_value=1)
    price = serializers.DecimalField(required=True, min_value=Decimal("0.00"), max_digits=10, decimal_places=2)

    class Meta:
        model = Services
        fields = "__all__"

    def validate_service_name(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Service name is required.")
        return str(value).strip()

    def validate_duration(self, value):
        if value <= 0:
            raise serializers.ValidationError("Duration must be greater than zero.")
        return value

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return value


class StaffServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffServices
        fields = "__all__"