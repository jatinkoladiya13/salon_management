from rest_framework import serializers

class BuyCreditSerializer(serializers.Serializer):
    price_id =  serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=99)

    def validate(self, attrs):

        if attrs["quantity"] > 99:
            raise serializers.ValidationError("Quantity should be less than 100")
        if attrs["quantity"] < 1:
            raise serializers.ValidationError("Quantity should be more than 0") 
        return super().validate(attrs)