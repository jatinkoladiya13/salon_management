from rest_framework import serializers


class ProductCheckoutSerializer(serializers.Serializer):
    cart_item_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False
    )