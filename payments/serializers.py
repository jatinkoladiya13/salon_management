from rest_framework import serializers
from .models import PaymentConfiguration, PaymentProvider

import stripe
import razorpay

class PaymentConfigurationSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = PaymentConfiguration
        fields = "__all__"

    def validate(self, attrs):
        provider = attrs.get("provider")
        credentials = attrs.get("payment_credentials") or {}

        if provider == PaymentProvider.STRIPE:
            self.validate_stripe(credentials)

        elif provider == PaymentProvider.RAZORPAY:
            self.validate_razorpay(credentials)

        branding_details = attrs.get("branding_details")
        if branding_details:
            self.validate_branding_details(branding_details)

        return attrs
    
    def validate_branding_details(self, branding_details):
        """
        Validates the branding_details JSON field.
        Ensures 'shop_name' and 'description' are present.
        """
        if not isinstance(branding_details, dict):
            raise serializers.ValidationError(
                {"branding_details": "Branding details must be a dictionary."}
            )

        shop_name = branding_details.get("shop_name")
        description = branding_details.get("description")

        errors = {}
        if not shop_name:
            errors["shop_name"] = "Shop name is required in branding details."
        if not description:
            errors["description"] = "Description is required in branding details."

        if errors:
            raise serializers.ValidationError({"branding_details": errors})
        return branding_details

    def validate_brand_logo(self, value):
        """
        Validates the brand_logo image field.
        Ensures file size is within limits and file type is an image.
        """
        if value:
            # 2MB size limit
            if value.size > 2 * 1024 * 1024:
                raise serializers.ValidationError("Brand logo image size cannot exceed 2MB.")

            allowed_extensions = ["jpeg", "jpg", "png"]
            if value.name.split(".")[-1].lower() not in allowed_extensions:
                raise serializers.ValidationError("Only JPEG, JPG, and PNG images are allowed.")
        return value
    
    def validate_stripe(self, credentials):
        secret_key = credentials.get("stripe_secret_key")
        publishable_key = credentials.get("stripe_public_key")
        mode = credentials.get("mode", "test")

        if not secret_key:
            raise serializers.ValidationError(
                {
                    "payment_credentials": {
                        "stripe_secret_key": "This field is required."
                    }
                }
            )

        if not publishable_key:
            raise serializers.ValidationError(
                {
                    "payment_credentials": {
                        "stripe_public_key": "This field is required."
                    }
                }
            )

        if mode not in ["test", "live"]:
            raise serializers.ValidationError(
                {
                    "payment_credentials": {
                        "mode": "Mode must be 'test' or 'live'."
                    }
                }
            )

        stripe.api_key = secret_key

        try:
            stripe.Account.retrieve()
        except Exception as e:
            raise serializers.ValidationError(
                {
                    "payment_credentials": {
                        "stripe_secret_key": f"Invalid Stripe credentials. {str(e)}"
                    }
                }
            )

    def validate_razorpay(self, credentials):
        key_id = credentials.get("razorpay_key_id")
        key_secret = credentials.get("razorpay_key_secret")
        mode = credentials.get("mode", "test")

        if not key_id:
            raise serializers.ValidationError(
                {
                    "payment_credentials": {
                        "razorpay_key_id": "This field is required."
                    }
                }
            )

        if not key_secret:
            raise serializers.ValidationError(
                {
                    "payment_credentials": {
                        "razorpay_key_secret": "This field is required."
                    }
                }
            )

        if mode not in ["test", "live"]:
            raise serializers.ValidationError(
                {
                    "payment_credentials": {
                        "mode": "Mode must be 'test' or 'live'."
                    }
                }
            )

        try:
            client = razorpay.Client(auth=(key_id, key_secret))

            # Verify credentials by fetching account payments
            client.payment.all({"count": 1})

        except razorpay.errors.BadRequestError as e:
            raise serializers.ValidationError(
                {
                    "payment_credentials": {
                        "razorpay_key_secret": f"Invalid Razorpay credentials. {str(e)}"
                    }
                }
            )

        except razorpay.errors.ServerError as e:
            raise serializers.ValidationError(
                {
                    "payment_credentials": {
                        "server": f"Razorpay server error. {str(e)}"
                    }
                }
            )

        except Exception as e:
            raise serializers.ValidationError(
                {
                    "payment_credentials": {
                        "error": f"Unable to verify Razorpay credentials. {str(e)}"
                    }
                }
            )