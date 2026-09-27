from rest_framework import serializers
from salonDetails.models import SalonDetails
from tenant.serializers import TeantSerializer

class SalonDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalonDetails
        fields = "__all__"
        read_only_fields = ["id", "slug"]

class SalonDetailsCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalonDetails
        fields = "__all__"

    def to_representation(self, instance):
        return SalonDetailsSerializer(instance).data        

    def validate_company_logo(self, value):
        if value:
            if value.size > 1024 * 1024 * 1:
                raise serializers.ValidationError(
                    "Image size should not exceed 1MB"
                )
            
            if value.name.split(".")[-1] not in ["jpeg", "jpg", "png"]:
                raise serializers.ValidationError(
                    "Only jpeg/jpg/png image is allowed"
                )
            
        return value
    
class SalongDetailsRetrieveSerializer(serializers.ModelSerializer):
    # Tenant.salonDetails declares related_name="salong_for_tenant"; the old
    # "tenant_for_salon" attribute does not exist on SalonDetails, so every
    # retrieve raised AttributeError before reaching the client.
    salong_for_tenant = TeantSerializer(read_only=True)

    class Meta:
        model = SalonDetails
        fields = "__all__"
        read_only_fields = ["id", "slug"]

class SalonOpeningHourSerializer(serializers.ModelSerializer):
    pass
    # opening_time = serializers.TimeField(
    #     format="%I:%M %p",
    #     input_formats=["%I:%M %p", "%H:%M"],
    #     required=False
    # )
    # closing_time = serializers.TimeField(
    #     format="%I:%M %p",
    #     input_formats=["%I:%M %p", "%H:%M"],
    #     required=False
    # )
    # class Meta:
    #     model = SalonOpeningHour
    #     fields = "__all__"
        