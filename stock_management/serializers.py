from django.db import transaction

from rest_framework import serializers

from .models import StockPurchase, StockPurchaseItem

class StockPurchaseItemSerializer(serializers.ModelSerializer):
    # Writable so an update can address an existing line. With the default
    # read-only pk the id never reached validated_data, so every update deleted
    # and recreated the whole item set instead of editing it.
    id = serializers.UUIDField(required=False)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockPurchaseItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "purchase_price",
            "subtotal",
        ]
        read_only_fields = ["subtotal"]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_purchase_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Purchase price cannot be negative.")
        return value


class StockPurchaseSerializer(serializers.ModelSerializer):
    items = StockPurchaseItemSerializer(many=True)

    class Meta:
        model = StockPurchase
        fields = [
            "id",
            "supplier_details",
            "invoice_number",
            "purchase_date",
            "payment_status",
            "total_amount",
            "items",
        ]
        read_only_fields = ["id", "total_amount"]

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError(
                "A stock purchase needs at least one item."
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")

        purchase = StockPurchase.objects.create(**validated_data)

        for item in items_data:
            item.pop("id", None)
            StockPurchaseItem.objects.create(
                stock_purchase=purchase,
                **item
            )

        purchase.refresh_from_db()
        purchase.recalc_total()

        return purchase

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if items_data is not None:
            item_ids = {item["id"] for item in items_data if item.get("id")}

            # Reject ids that belong to a different purchase before touching
            # anything, so a bad payload cannot delete this purchase's lines.
            known_ids = set(
                instance.items.values_list("id", flat=True)
            )
            unknown = item_ids - known_ids
            if unknown:
                raise serializers.ValidationError(
                    {
                        "items": [
                            f"Item {item_id} does not belong to this purchase."
                            for item_id in sorted(str(i) for i in unknown)
                        ]
                    }
                )

            # list(): each delete() writes to the product row, and iterating a
            # queryset while mutating it is unsafe.
            for item in list(instance.items.all()):
                if item.id not in item_ids:
                    item.delete()

            for item in items_data:
                item_id = item.pop("id", None)
                if item_id:
                    # Update existing item
                    stock_item = StockPurchaseItem.objects.get(
                        id=item_id, stock_purchase=instance
                    )
                    stock_item.product = item.get("product", stock_item.product)
                    stock_item.quantity = item.get("quantity", stock_item.quantity)
                    stock_item.purchase_price = item.get(
                        "purchase_price", stock_item.purchase_price
                    )
                    stock_item.save()
                else:
                    # Create new item
                    StockPurchaseItem.objects.create(stock_purchase=instance, **item)

        instance.refresh_from_db()
        instance.recalc_total()

        return instance