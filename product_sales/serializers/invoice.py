from django.db import transaction
from rest_framework import serializers
from product_sales.models import Invoice, InvoiceItem, CartItem


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
        cart_items = CartItem.objects.filter(user=user)

        if not cart_items.exists():
            raise serializers.ValidationError("Your cart is empty.")

        with transaction.atomic():
            validated_data["user"] = user
            invoice = Invoice.objects.create(**validated_data)

            invoice_items = []
            for item in cart_items:
                invoice_items.append(
                    InvoiceItem(invoice=invoice, product=item.product, quantity=item.quantity, price=item.price)
                )
            InvoiceItem.objects.bulk_create(invoice_items)
            cart_items.delete()
            invoice.recalc_total()
        return invoice