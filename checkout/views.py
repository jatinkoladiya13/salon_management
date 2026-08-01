from django.db import transaction
from django.utils import timezone
from django.conf import settings

from rest_framework.views import Response, APIView
from rest_framework import permissions, status

from subscription.models import SubscriptionPlan
from tenant.models import Tenant

from payments.models import PaymentConfiguration, PaymentProvider
from payments.services.stripe import StripePaymentService
from payments.services.razorpay import RazorpayPaymentService


from product_sales.models import CartItem, Invoice
from .serializers import ProductCheckoutSerializer

from utils.permissions import IsAdmin
import utils.response_handler as rh 

from decouple import config
from decimal import Decimal
from uuid import uuid4
import datetime

import stripe
import razorpay

# Create your views here.

def get_stripe_customer_id(tenant, user):

    customer_org = tenant.salonDetails

    if  tenant.stripe_customer_id is not None:
        # Customer already exists on Stripe
        stripe_customer_id = tenant.stripe_customer_id
    else: 
        address = {
            "line1": customer_org.address,
            "city": customer_org.city,
            "state": customer_org.state,
            "postal_code": str(customer_org.postal_code),
            "country": customer_org.country,
        }

        # Customer doesn't exist, create a new one
        stripe_customer = stripe.Customer.create(
            name=customer_org.name,
            email=customer_org.organization_email
            if customer_org.organization_email
            else user.email,
            address=address,
        )

        tenant.stripe_customer_id = stripe_customer.id
        tenant.save()
        stripe_customer_id = stripe_customer.id 

    return stripe_customer_id

class CheckoutSessionview(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        """
        Create a new checkout subscriptions session
        """
        address = True
        
        price_id = request.data.get("price_id")
        if not price_id:
            response = rh.ResponseMsg(
                {},
                True,
                "Pricing ID is required in the request body",
            )
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data=response.response
            )
        
        if  (
            request.tenant.subscription_status == "active"
            and request.tenant.subscription_plan.interval != "trial"
        ):
            response = rh.ResponseMsg(
                {},
                True,
                "Subscription already active, you can only upgrade or downgrade your subscription plan",
            )
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data=response.response
            )
        
        try:
            subscription_plan = SubscriptionPlan.objects.get(
                stripe_price_id=price_id
            )
        except SubscriptionPlan.DoesNotExist:
            response = rh.ResponseMsg(
                {},
                True,
                "Invalid subscription plan"
            )
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=response.response
            )
        
        price = subscription_plan.stripe_price  

        # stripe.api_key = config("STRIPE_SECRET_KEY")
        stripe.api_key = settings.STRIPE_SECRET_KEY

        tenant = Tenant.objects.get(schema_name=request.tenant.schema_name)

        stripe_customer_id = get_stripe_customer_id(tenant, request.user)
        if not stripe_customer_id:
            address = False
            response = rh.ResponseMsg(
                {"address": address},
                False,
                "Checkout session created successfully!!!",
            )
            return Response(status=status.HTTP_200_OK, data=response.response)
        
        # generate a uuid4
        uid = uuid4()

        session_data = {
            "type": "new_subscription",
            "uid": uid,
            "schema_name": request.tenant.schema_name,
            "organisation_id": tenant.stripe_customer_id,
            "user_id": str(request.user.id),
            "plan_id":str(subscription_plan.id)
        }

        expired_time = int(
            (
                datetime.datetime.now() + datetime.timedelta(minutes=30)
            ).timestamp()
        )

        # Create a Checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": price.id,
                    "quantity": 1,
                },
            ],
            mode="subscription",
            success_url=f'{config("HTTP_PROXY")}{request.tenant.schema_name}.{config("HOST_URI")}/payment-confirmation/success',
            cancel_url=f'{config("HTTP_PROXY")}{request.tenant.schema_name}.{config("HOST_URI")}/payment-confirmation/failed',
            customer=stripe_customer_id,
            # Associate the session with the customer ID
            metadata=session_data,
            expires_at=expired_time,
            allow_promotion_codes=True,
            # subscription_data={
            # 'trial_period_days': 14  # 14-day free trial
            # }
        )

        response = rh.ResponseMsg(
            {"checkout_url": session.url, "address": address},
            False,
            "Checkout session created successfully!!!",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)


 

class ProductCheckoutSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        Create a new checkout subscriptions session
        """

        serializer = ProductCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart_item_ids = serializer.validated_data["cart_item_ids"]
        user = request.user
        customer_email = user.email

        cart_items = (
            CartItem.objects
            .select_related("product")
            .filter(
                id__in=cart_item_ids,
                user=user
            )
        )
        
        if cart_items.count() != len(cart_item_ids):
            response = rh.ResponseMsg(
                {},
                True,
                "Some cart items are invalid.",
            )
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data=response.response
            )
        
        payment_config = PaymentConfiguration.objects.filter(is_active=True).first()
        if not payment_config:
            response = rh.ResponseMsg(
                {},
                True,
                "No active payment configuration found",
            )
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data=response.response
            )
        
        line_items = [
            {
                'price_data': {
                    'currency': payment_config.currency.lower(), # e.g., 'inr'
                    'product_data': {
                        "name": cart_item.product.name,
                        "metadata": {
                            "product_id": str(cart_item.product.id),
                            "cart_item_id": str(cart_item.id),
                        },
                    },
                    'unit_amount': int(cart_item.price),
                },
                'quantity': cart_item.quantity,
            }
          
            for cart_item in cart_items
        ]

        metadata={
            "tenant_id": str(request.tenant.id),
            "user_id": str(request.user.id),
            "type": "product_purchase",
        }
        
        if payment_config.provider ==  PaymentProvider.STRIPE:
         
            payment_service = StripePaymentService(payment_config)
            session = payment_service.create_checkout_session(
                line_items=line_items,
                success_url=f'{config("HTTP_PROXY")}{request.tenant.schema_name}.{config("HOST_URI")}/payment-confirmation/success',
                cancel_url=f'{config("HTTP_PROXY")}{request.tenant.schema_name}.{config("HOST_URI")}/payment-confirmation/failed',
                customer_email=customer_email,
                metadata=metadata,
                allow_promotion_codes=True,
            )

            data = {
                "checkout_url": session.url,
                "user": {
                    "name": user.username,
                    "email": user.email,
                    "mobile": user.mobile
                }
            }
            response = rh.ResponseMsg(
                data,
                False,
                "Checkout session created successfully!!!",
            )
            return Response(status=status.HTTP_200_OK, data=response.response)

        elif payment_config.provider ==  PaymentProvider.RAZORPAY:
            payment_service = RazorpayPaymentService(payment_config)
            razorpay_order = payment_service.create_checkout_session(
                line_items=line_items,
                metadata=metadata,
            )

            payment_credentials = payment_config.payment_credentials or {}
            public_key = payment_credentials.get("razorpay_key_id")

            invoice_number = f"INV-{timezone.now().strftime('%Y%m%d%H%M%S')}" 
            invoice = Invoice.objects.create(
                invoice_number=invoice_number,
                user=user,
                phone=user.mobile,
                shipping_address=user.address,
                payment_method="card",
                payment_status="Unpaid",
                total_amount=Decimal(razorpay_order['amount'] or 0),
                razorpay_order_id=razorpay_order['id'],
                order_status="pending",
                # discount=discount_amount,
                # tax=tax_amount,
            )
            invoice.save()

 
            data = {
                'razorpay_order_id': razorpay_order['id'],
                'amount': razorpay_order['amount'],
                'currency': razorpay_order['currency'],
                'razorpay_key': public_key,
                "user": {
                    "name": user.username,
                    "email": user.email,
                    "mobile": user.mobile
                }
            }

            response = rh.ResponseMsg(
                data,
                False,
                "Checkout session created successfully!!!",
            )
            return Response(status=status.HTTP_200_OK, data=response.response)


class VerifyRazorpayPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):

        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature = request.data.get('razorpay_signature')

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            response = rh.ResponseMsg(
                {},
                True,
                "Missing payment parameters",
            )
            return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)

        invoice  = Invoice.objects.select_for_update().get(
            razorpay_order_id=razorpay_order_id,
            user=request.user
        )

        if not invoice:
            response = rh.ResponseMsg(
                {},
                True,
                "Invoice not found",
            )
            return Response(status=status.HTTP_404_NOT_FOUND, data=response.response) 

        if invoice.payment_status == "paid":
            response = rh.ResponseMsg(
                {},
                True,
                "Payment already verified",
            )
            return  Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)

        config = PaymentConfiguration.objects.get(
            provider=PaymentProvider.RAZORPAY,
            is_active=True
        )

        payment_credentials = config.payment_credentials or {}
        public_key = payment_credentials.get("razorpay_key_id")
        secret_key = payment_credentials.get("razorpay_key_secret")
        
        client = razorpay.Client(
            auth=(public_key, secret_key)
        )

        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
        except razorpay.errors.SignatureVerificationError:
            response = rh.ResponseMsg(
                {},
                True,
                "Invalid signature.",
            )
            return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)

        invoice.razorpay_payment_id  = razorpay_payment_id
        invoice.payment_status = "paid"
        invoice.save()

        response = rh.ResponseMsg(
            {},
            False,
            "Payment verified successfully",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)