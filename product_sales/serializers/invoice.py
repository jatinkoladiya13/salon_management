from django.db import transaction
from rest_framework import serializers
from product_sales.models import (
    CartItem,
    Invoice,
    InvoiceItem,
    Product,
    build_invoice_number,
)


class InvoiceItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = InvoiceItem
        fields = ("id", "product_name", "quantity", "price", "subtotal")


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = (
            "id",
            "invoice_number",
            "shipping_address",
            "invoice_date",
            "discount",
            "tax",
            "total_amount",
            "payment_method",
            "payment_status",
            "order_status",
            "items",
        )
        read_only_fields = (
            "id",
            "invoice_number",
            "invoice_date",
            "total_amount",
            "payment_status",
            "order_status",
            "items",
        )

    def create(self, validated_data):
        user = self.context["request"].user

        with transaction.atomic():
            cart_items = list(
                CartItem.objects.select_related("product").filter(user=user)
            )

            if not cart_items:
                raise serializers.ValidationError("Your cart is empty.")

            # Lock the products so two concurrent checkouts cannot both pass
            # the availability check and oversell the same units.
            product_ids = [item.product_id for item in cart_items]
            locked_products = {
                product.id: product
                for product in Product.objects.select_for_update().filter(
                    id__in=product_ids
                )
            }

            unavailable = [
                item.product.name
                for item in cart_items
                if item.quantity > locked_products[item.product_id].current_stock
            ]
            if unavailable:
                raise serializers.ValidationError(
                    {
                        "items": "Not enough stock for: " + ", ".join(unavailable),
                    }
                )

            validated_data["user"] = user
            # invoice_number is read-only on this serializer and was never
            # populated, so every invoice was saved with an empty string and
            # the second one violated the unique constraint.
            validated_data["invoice_number"] = build_invoice_number()
            invoice = Invoice.objects.create(**validated_data)

            # Created one at a time on purpose: InvoiceItem.save() is what
            # decrements Product.current_stock, and bulk_create() bypasses it,
            # so the old code sold stock it never took off the shelf.
            for item in cart_items:
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=item.product,
                    quantity=item.quantity,
                    price=item.price,
                )

            CartItem.objects.filter(user=user).delete()
            invoice.recalc_total()

        return invoice