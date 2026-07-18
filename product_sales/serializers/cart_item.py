from django.db import transaction
from rest_framework import serializers
from product_sales.models import CartItem, Product


class CartItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ("id", "product", "    ", "price", "subtotal")
        read_only_fields = ("id", "price", "subtotal")

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be a positive number.")
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        product = validated_data["product"]
        quantity = validated_data["quantity"]

        if quantity > product.current_stock:
            raise serializers.ValidationError(
                f"Not enough stock for {product.name}. "
                f"Available: {product.current_stock}, requested: {quantity}"
            )

        with transaction.atomic():
            cart_item, created = CartItem.objects.get_or_create(
                user=user,
                product=product,
                defaults={"quantity": quantity, "price": product.selling_price},
            )

            if not created:
                new_quantity = cart_item.quantity + quantity
                if new_quantity > product.current_stock:
                    raise serializers.ValidationError(f"Not enough stock for {product.name}.")
                cart_item.quantity = new_quantity
                cart_item.save()

        return cart_item

    def update(self, instance, validated_data):
        product = instance.product
        quantity = validated_data.get("quantity", instance.quantity)

        if quantity > product.current_stock:
            raise serializers.ValidationError(
                f"Not enough stock for {product.name}. "
                f"Available: {product.current_stock}, requested: {quantity}"
            )

        instance.quantity = quantity
        instance.save()

        return instance