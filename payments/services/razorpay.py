import razorpay
from decimal import Decimal


class RazorpayPaymentService:
    """
    Razorpay Payment Service
    """

    def __init__(self, payment_config):
        self.payment_config = payment_config
                
        credentials = payment_config.payment_credentials or {}
        
        self.mode = credentials.get("mode", "test")
        self.key_id = credentials.get("razorpay_key_id")
        self.key_secret = credentials.get("razorpay_key_secret")

        self.client = razorpay.Client(auth=(self.key_id, self.key_secret))

    def create_checkout_session(
        self,
        *,
        line_items,
        success_url=None,
        cancel_url=None,
        customer_email=None,
        metadata=None,
        **kwargs
    ):
        """
        Creates a Razorpay order.
        Razorpay doesn't have a "checkout session" URL like Stripe.
        Instead, we create an order and return the order details.
        The frontend will use these details with Razorpay's checkout.js.
        """
        total_amount = sum(
            Decimal(item['price_data']['unit_amount']) * item['quantity']
            for item in line_items
        )

        order_data = {
            'amount': int(total_amount),  # Amount in the smallest currency unit (e.g., paisa)
            'currency': self.payment_config.currency.upper(),
            'notes': metadata,
        }

        try:
            razorpay_order = self.client.order.create(order_data)
            return razorpay_order
        except Exception as e:
            raise e