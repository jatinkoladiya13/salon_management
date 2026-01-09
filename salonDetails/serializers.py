from rest_framework import serializers
from salonDetails.models import SalonDetails, SalonOpeingHour
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
    tenant_for_salon = TeantSerializer(read_only =True)
    
    class Meta:
        model = SalonDetails
        fields = "__all__"
        read_only_fields = ["id", "slug"]

