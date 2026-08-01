



import stripe


class StripePaymentService:
    """
    Stripe Payment Service
    """
    def __init__(self, payment_config):
        self.payment_config = payment_config
        
        credentials = payment_config.payment_credentials or {}
        
        self.mode = credentials.get("mode", "test")
        self.publishable_key = credentials.get("stripe_public_key")
        self.secret_key = credentials.get("stripe_secret_key")
        self.automatic_tax_enabled = self.mode == "live"
        self.tax_id_collection_enabled = self.mode == "live"

        stripe.api_key = self.secret_key

    def create_checkout_session(
        self,
        *,
        line_items,
        success_url,
        cancel_url,
        customer_email=None,
        metadata=None,
        allow_promotion_codes=False,
        automatic_tax=None,
        tax_id_collection=None,
    ):
        """
        amount = smallest currency unit
        Example:
            INR 100 = 10000
            USD 100 = 10000
        """
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=customer_email,
                metadata=metadata,
                allow_promotion_codes=allow_promotion_codes,
                automatic_tax={"enabled": self.automatic_tax_enabled if automatic_tax is None else automatic_tax.get("enabled", self.automatic_tax_enabled)},
                tax_id_collection={"enabled": self.tax_id_collection_enabled if tax_id_collection is None else tax_id_collection.get("enabled", self.tax_id_collection_enabled)},
            )
            return session
        except Exception as e:
            raise e