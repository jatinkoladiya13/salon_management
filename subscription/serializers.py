from djstripe.models import Price, Invoice
from rest_framework import serializers
from subscription.models import SubscriptionPlan

class PriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Price
        fields = (
            "djstripe_id",
            "id",
            "livemode",
            "active",
            "currency",
            "type",
            "unit_amount",
            "unit_amount_decimal",
            "billing_scheme",
            "lookup_key",
            "tiers",
            "tiers_mode",
            "transform_quantity",
            "djstripe_owner_account",
            "product",
            # "name",
        )

    def get_name(self, obj):
        return f"{obj.human_readable_price} for {obj.product.name}"
    
class PriceBasicSerializer(PriceSerializer):
    class Meta:
        model = Price
        fields = ("djstripe_id",)  #"name"

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
    stripe_price = PriceBasicSerializer(read_only=True)        

    class Meta:
        model = SubscriptionPlan
        fields = "__all__"

class SubscriptionPlanCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = "__all__"

    def to_representation(self, instance):
        return SubscriptionPlanGetSerializer(instance).data


class SubscriptionPlanTypeGETSerializer(serializers.ModelSerializer):
    pass
    # subscription_plans = SubscriptionPlanGetSerializer(
    #     read_only=True, many=True
    # )

    # class Meta:
    #     model = SubscriptionPlanType
    #     fields = "__all__"


class SubscriptionPlanTypeCreateUpdateSerializer(serializers.ModelSerializer):
    pass
    # class Meta:
    #     model = SubscriptionPlanType
    #     fields = "__all__"

    # def to_representation(self, instance):
    #     return SubscriptionPlanTypeGETSerializer(instance).data    