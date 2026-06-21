from djstripe.models import  Product, Price, Invoice
from rest_framework import serializers
from subscription.models import SubscriptionPlan

class PriceSerializer(serializers.ModelSerializer):
    amount = serializers.SerializerMethodField()

    class Meta:
        model = Price
        fields = [
            "id",
            "djstripe_id",
            "currency",
            "amount",
            "type",
            "active",
        ]

    def get_amount(self, obj):
        if obj.unit_amount:
            return obj.unit_amount / 100
        return 0

    
class ProductSerializer(serializers.ModelSerializer):
    prices = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "djstripe_id",
            "name",
            "description",
            "active",
            "prices",
        ]

    def get_prices(self, obj):
        prices = Price.objects.filter(
            product=obj,
            active=True
        )

        return PriceSerializer(prices, many=True).data

class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        fiedls = (
            "id",
            "created",
            "billing_reason",
            "amount_due",
            "amount_paid",
            "amount_remaining",
            "currency",
            "hosted_invoice_url",
            "invoice_pdf",
            "status",
        )

class SubscriptionPlanGetSerializer(serializers.ModelSerializer):
    stripe_price = PriceSerializer(read_only=True)        

    class Meta:
        model = SubscriptionPlan
        fields = "__all__"

class SubscriptionPlanCreateUpdateSerializer(serializers.ModelSerializer):
    # stripe_price = serializers.CharField()
    class Meta:
        model = SubscriptionPlan
        fields = "__all__"

    def to_representation(self, instance):
        return SubscriptionPlanGetSerializer(instance).data
