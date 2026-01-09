from rest_framework import serializers
from tenant.models import Tenant, Domain

class TeantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant 
        fields = "__all__"
        read_only_fields = ["created_on"]

class TenantDomainSerializer(serializers.Serializer):
    tenant_name = serializers.CharField(required=True, max_length=100)
    domain_name = serializers.CharField(required=True, max_length =100)
    customer  = serializers.IntegerField(required=True)

class UpdateDomainSerializer(serializers.Serializer):
    domain_name = serializers.CharField(required=True, max_length=100)

    class Meta:
        model = Domain
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]           