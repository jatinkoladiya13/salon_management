from django_tenants.utils import schema_context
from django.conf import settings
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from djstripe.models import Price

from rest_framework.views import Response, APIView
from rest_framework.permissions import AllowAny
from rest_framework import status

from product_sales.models import Product
from product_sales.models import Invoice, InvoiceItem
from product_sales.models import CartItem


from payments.models import PaymentConfiguration

from subscription.models import SubscriptionPlan
from tenant.models import Tenant

import utils.response_handler as rh 

import logging
import json

import stripe
import razorpay

# Create your views here.

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

class StripeWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        payload  = request.body
        sig_header = request.headers.get('STRIPE_SIGNATURE')

        try:
            event = stripe.Webhook.construct_event(
                payload,
                sig_header,
                settings.DJSTRIPE_WEBHOOK_SECRET
            )

        except ValueError:
            logger.exception("Invalid Stripe payload")
            return Response(
                {"error": "Invalid payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        except stripe.error.SignatureVerificationError:
            logger.exception("Invalid Stripe signature")
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_type = event["type"]

        logger.info("Stripe Event Received: %s", event_type)  

        handler_map = {
            "checkout.session.completed": self.handle_checkout_completed,
            "invoice.payment_succeeded": self.handle_invoice_payment_succeeded,
            "invoice.payment_failed": self.handle_invoice_payment_failed,
            "customer.subscription.deleted": self.handle_subscription_deleted,
        }

        handler = handler_map.get(event_type)
        
        if handler:
            handler(event)
        return Response(status=status.HTTP_200_OK)
        
    def get_expiry_date(self, interval):
        days = 365 if interval == "yearly" else 30
        return timezone.now().date() + timedelta(days=days) 
    
    def update_tenant_subscription(
        self,
        tenant,
        subscription_plan,
        subscription_id,
        status_value="active",
    ):
        tenant.subscription_status = status_value
        tenant.subscription_plan = subscription_plan
        tenant.subscription_end_date = self.get_expiry_date(
            subscription_plan.interval
        )
        tenant.stripe_subscription_id = subscription_id

        tenant.save(
            update_fields=[
                "subscription_status",
                "subscription_plan",
                "subscription_end_date",
                "stripe_subscription_id",
            ]
        )

    def handle_checkout_completed(self, event):

        session = event["data"]["object"]

        if session.get("payment_status") != "paid":
            return

        metadata = session.get("metadata", {})

        if metadata.get("type") != "new_subscription":
            return

        try:
            tenant = Tenant.objects.get(
                schema_name=metadata["schema_name"]
            )

            plan = SubscriptionPlan.objects.get(
                id=metadata["plan_id"]
            )

            self.update_tenant_subscription(
                tenant=tenant,
                subscription_plan=plan,
                subscription_id=session.get("subscription"),
            )

            logger.info(
                "New subscription activated for %s",
                tenant.schema_name,
            )

        except Exception:
            logger.exception("Checkout Session Processing Failed")

    def handle_invoice_payment_succeeded(self, event):

        invoice = event["data"]["object"]
        metadata = invoice.get("metadata", {})

        if metadata.get("type") == "upgrade_subscriptions":
            self.handle_upgrade_subscription(invoice)
            return

        billing_reason = invoice.get("billing_reason")

        if billing_reason in [
            "subscription_create",
            "subscription_cycle",
        ]:
            self.handle_subscription_renewal(invoice)

    def handle_upgrade_subscription(self, invoice):

        try:
            tenant = Tenant.objects.get(
                schema_name=invoice["metadata"]["schema_name"]
            )

            plan = SubscriptionPlan.objects.get(
                id=invoice["metadata"]["upgrade_plan_id"]
            )

            self.update_tenant_subscription(
                tenant=tenant,
                subscription_plan=plan,
                subscription_id=invoice["metadata"]["new_subscription_id"],
            )

            logger.info(
                "Subscription upgraded for %s",
                tenant.schema_name,
            )

        except Exception:
            logger.exception("Upgrade Subscription Failed")

    def handle_subscription_renewal(self, invoice):

        try:
            price_id = invoice["lines"]["data"][0]["pricing"][
                "price_details"
            ]["price"]

            stripe_subscription_id = invoice["parent"][
                "subscription_details"
            ]["subscription"]

            stripe_price = Price.objects.get(id=price_id)

            plan = SubscriptionPlan.objects.get(
                stripe_price=stripe_price
            )

            tenant = Tenant.objects.get(
                stripe_customer_id=invoice["customer"]
            )

            self.update_tenant_subscription(
                tenant=tenant,
                subscription_plan=plan,
                subscription_id=stripe_subscription_id,
            )

            logger.info(
                "Subscription renewed for %s",
                tenant.schema_name,
            )

        except Exception:
            logger.exception("Renewal Processing Failed")

    def handle_invoice_payment_failed(self, event):

        invoice = event["data"]["object"]

        try:
            tenant = Tenant.objects.get(
                stripe_customer_id=invoice["customer"]
            )

            tenant.subscription_status = "past_due"

            tenant.save(
                update_fields=["subscription_status"]
            )

            logger.warning(
                "Payment failed for %s",
                tenant.schema_name,
            )

        except Tenant.DoesNotExist:
            logger.warning(
                "Tenant not found: %s",
                invoice["customer"],
            )

    def handle_subscription_deleted(self, event):

        subscription = event["data"]["object"]

        try:
            tenant = Tenant.objects.get(
                stripe_customer_id=subscription["customer"]
            )

            tenant.subscription_status = "expired"
            tenant.subscription_plan = None
            tenant.stripe_subscription_id = None

            tenant.save(
                update_fields=[
                    "subscription_status",
                    "subscription_plan",
                    "stripe_subscription_id",
                ]
            )

            logger.info(
                "Subscription expired for %s",
                tenant.schema_name,
            )

        except Tenant.DoesNotExist:
            logger.warning(
                "Tenant not found: %s",
                subscription["customer"],
            )

class StripeProductWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, tenant_id):

        payload  = request.body
        sig_header = request.headers.get('STRIPE_SIGNATURE')

        try:
            tenant = Tenant.objects.get(id=tenant_id)

        except Tenant.DoesNotExist:

            logger.error("Tenant not found: %s", tenant_id)

            return Response(
                {"error": "Invalid tenant"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        with schema_context(tenant.schema_name):
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

        try:
            event = stripe.Webhook.construct_event(
                payload,
                sig_header,
                payment_config.webhook_secret
            )

        except ValueError:
            logger.exception("Invalid Stripe payload")
            return Response(
                {"error": "Invalid payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        except stripe.error.SignatureVerificationError:
            logger.exception("Invalid Stripe signature")
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_type = event["type"]    

        if event_type == "checkout.session.completed":
          
            session = event["data"]["object"]
            customer_email = session.get("customer_details", {}).get("email")

            if not customer_email:
                logger.error("No customer email in checkout session.")
                return Response(status=status.HTTP_400_BAD_REQUEST)

            with schema_context(tenant.schema_name), transaction.atomic():
                try:
                    User = get_user_model()
                    user = User.objects.get(email=customer_email)

                    checkout_session_id = session.get("id")
                    existing_invoice = Invoice.objects.filter(
                        stripe_checkout_session_id=checkout_session_id
                    ).first()

                    if existing_invoice:
                        logger.info(
                            "Invoice already exists for checkout session %s",
                            checkout_session_id,
                        )
                        return Response(status=status.HTTP_200_OK)

                    total_details = session.get("total_details", {}) or {}
                    discount_amount = Decimal(total_details.get("amount_discount") or 0)
                    tax_amount = Decimal(total_details.get("amount_tax") or 0)

                    # 1. Create the invoice
                    invoice_number = f"INV-{timezone.now().strftime('%Y%m%d%H%M%S')}"
                    invoice = Invoice.objects.create(
                        invoice_number=invoice_number,
                        user=user,
                        phone=user.mobile,
                        shipping_address=user.address,
                        payment_method="card",
                        payment_status="paid",
                        order_status="confirmed",
                        total_amount=Decimal(session["amount_total"] or 0),
                        discount=discount_amount,
                        tax=tax_amount,
                        stripe_checkout_session_id=checkout_session_id,
                    )
                    logger.info(
                        "Created invoice %s for user %s with discount %s and tax %s",
                        invoice.invoice_number,
                        user.email,
                        discount_amount,
                        tax_amount,
                    )

                    # Retrieve line items from Stripe session for accuracy
                    line_items = stripe.checkout.Session.list_line_items(session["id"], expand=["data.price.product"])

                    cart_item_ids_to_delete = []
                    for item in line_items.data:
                        product_id = item.price.product.metadata.get("product_id")
                        cart_item_id = item.price.product.metadata.get("cart_item_id")
                        if cart_item_id:
                            cart_item_ids_to_delete.append(cart_item_id)

                        try:
                            product = Product.objects.get(id=product_id)
                            # 2. Create invoice item, leveraging model's save() method to handle stock
                            InvoiceItem.objects.create(
                                invoice=invoice,
                                product=product,
                                quantity=item.quantity,
                                price=Decimal(item.price.unit_amount or 0),
                            )
                        except Product.DoesNotExist:
                            logger.error(f"Product with ID {product_id} not found for invoice {invoice.invoice_number}.")
                            # Optionally, raise an exception here to fail the transaction

                    # 3. Recalculate invoice total based on created items
                    invoice.recalc_total()

                    # 4. Remove purchased items from the cart
                    if cart_item_ids_to_delete:
                        CartItem.objects.filter(user=user, id__in=cart_item_ids_to_delete).delete()
                        logger.info(f"Cleared {len(cart_item_ids_to_delete)} items from cart for user {user.email}")

                except Exception as e:
                    logger.error(f"Error processing checkout for {customer_email}: {e}")
                    return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.info("Stripe Event:\n%s", json.dumps(event, indent=4))

        return Response(status=status.HTTP_200_OK)


class RazorpayWebhookView(APIView):
    permission_classes = [AllowAny]

    def create_invoice_items_from_invoice(self, invoice):
        if invoice.items.exists():
            return

        cart_items = (
            CartItem.objects.select_related("product")
            .filter(user=invoice.user)
            .order_by("product__name")
        )

        if not cart_items.exists():
            return

        with transaction.atomic():
            for cart_item in cart_items:
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=cart_item.product,
                    quantity=cart_item.quantity,
                    price=cart_item.price,
                )

            CartItem.objects.filter(user=invoice.user).delete()

    def post(self, request, tenant_id):
        webhook_signature = request.headers.get('X-Razorpay-Signature', '')

        # Request body must be read as raw bytes for signature validation
        webhook_body = request.body

        print("Received Razorpay webhook for tenant:", tenant_id)

        try:
            tenant = Tenant.objects.get(id=tenant_id)

        except Tenant.DoesNotExist:

            logger.error("Tenant not found: %s", tenant_id)

            return Response(
                {"error": "Invalid tenant"},
                status=status.HTTP_404_NOT_FOUND,
            )

        with schema_context(tenant.schema_name):
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

        payment_credentials = payment_config.payment_credentials or {}
        public_key = payment_credentials.get("razorpay_key_id")
        secret_key = payment_credentials.get("razorpay_key_secret")

        webhook_secret = payment_config.webhook_secret

        client = razorpay.Client(auth=(public_key, secret_key))

        try:
            # Verify the signature
            client.utility.verify_webhook_signature(
                webhook_body.decode('utf-8'), 
                webhook_signature, 
                webhook_secret
            )
        except razorpay.errors.SignatureVerificationError:
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)


        with schema_context(tenant.schema_name):
            # Parse valid payload
            data = request.data
            event_type = data.get('event')

            if event_type == 'payment.captured':
                payment_entity = data.get('payload', {}).get('payment', {}).get('entity', {})
                razorpay_order_id = payment_entity.get('order_id')
                razorpay_payment_id = payment_entity.get('id')

                invoice = Invoice.objects.filter(razorpay_order_id=razorpay_order_id).first()

                if invoice and invoice.payment_status != 'paid':
                    invoice.payment_status = 'paid'
                    invoice.razorpay_payment_id = razorpay_payment_id
                    invoice.save()

                if invoice and invoice.payment_status == 'paid':
                    self.create_invoice_items_from_invoice(invoice)

            elif event_type == 'payment.failed':
                failed_entity = data.get('payload', {}).get('payment', {}).get('entity', {})
                razorpay_order_id = failed_entity.get('order_id')

                Invoice.objects.filter(razorpay_order_id=razorpay_order_id).delete()

            print("razorpay Event:\n", json.dumps(event_type, indent=4))
            print("razorpay Data:\n", json.dumps(data, indent=4))
        
        return Response(status=status.HTTP_200_OK)



                   

        