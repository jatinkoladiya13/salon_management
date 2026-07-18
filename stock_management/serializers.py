from django.db import transaction

from rest_framework import serializers

from .models import StockPurchase, StockPurchaseItem

class StockPurchaseItemSerializer(serializers.ModelSerializer):
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
        read_only_fields = ["id", "subtotal"]


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

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")

        purchase = StockPurchase.objects.create(**validated_data)

        for item in items_data:
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
            item_ids = [item.get("id") for item in items_data if item.get("id")]
            
            # Delete items that are not in the payload
            for item in instance.items.all():
                if item.id not in item_ids:
                    item.delete()

            for item in items_data:
                item_id = item.get("id", None)
                if item_id:
                    # Update existing item
                    stock_item = StockPurchaseItem.objects.get(id=item_id, stock_purchase=instance)
                    stock_item.product = item.get("product", stock_item.product)
                    stock_item.quantity = item.get("quantity", stock_item.quantity)
                    stock_item.purchase_price = item.get("purchase_price", stock_item.purchase_price)
                    stock_item.save()
                else:
                    # Create new item
                    StockPurchaseItem.objects.create(stock_purchase=instance, **item)

        instance.refresh_from_db()
        instance.recalc_total()

        return instance