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
    invoice_number = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    amount_paid = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    invoice_pdf = serializers.SerializerMethodField()
    plan_name = serializers.SerializerMethodField()
    billing_reason = serializers.SerializerMethodField()
    customer_email = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    metadata = serializers.SerializerMethodField()


    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "status",
            "amount_paid",
            "currency",
            "plan_name",
            "invoice_pdf",
            "created",
            "billing_reason",
            "customer_email",
            "customer_phone",
            "customer",
            "metadata",
        ]

    def get_customer(self, obj):
        return obj.stripe_data.get("customer") 

    def get_metadata(self, obj):
        return obj.stripe_data.get("metadata", {}) 

    def get_customer_phone(self, obj):
        return obj.stripe_data.get("customer_phone")   
 
    def get_customer_email(self, obj):
        return obj.stripe_data.get("customer_email")

    def get_billing_reason(self, obj):
        return obj.stripe_data.get("billing_reason")
   
    def get_invoice_number(self, obj):
        return obj.stripe_data.get("number")

    def get_status(self, obj):
        return obj.stripe_data.get("status")

    def get_amount_paid(self, obj):
        return obj.stripe_data.get("amount_paid", 0) / 100

    def get_currency(self, obj):
        return obj.stripe_data.get("currency", "").upper()

    def get_invoice_pdf(self, obj):
        return obj.stripe_data.get("invoice_pdf")

    def get_plan_name(self, obj):
        try:
            return obj.stripe_data["lines"]["data"][0]["description"]
        except Exception:
            return None

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
