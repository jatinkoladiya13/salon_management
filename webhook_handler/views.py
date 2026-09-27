from django_tenants.utils import schema_context
from django.conf import settings
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from djstripe.models import Price

from rest_framework.views import Response, APIView
from rest_framework.permissions import AllowAny
from rest_framework import status

from product_sales.models import Product
from product_sales.models import Invoice, InvoiceItem, build_invoice_number
from product_sales.models import CartItem


from payments.models import PaymentConfiguration
from payments.money import from_minor_units

from subscription.models import SubscriptionPlan
from tenant.models import Tenant

import utils.response_handler as rh 

import logging

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
        # SubscriptionPlan.INTERVAL_CHOICES uses "year"/"month", never
        # "yearly" - so annual plans were silently expiring after 30 days.
        days = 365 if interval in ("year", "yearly") else 30
        # subscription_end_date is a DateTimeField and is compared against
        # timezone.now() during authentication, so return an aware datetime
        # rather than a bare date.
        return timezone.now() + timedelta(days=days)
    
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

                    # Stripe reports every amount in the smallest currency
                    # unit; the columns hold major units.
                    currency = session.get("currency") or payment_config.currency
                    total_details = session.get("total_details", {}) or {}
                    discount_amount = from_minor_units(
                        total_details.get("amount_discount"), currency
                    )
                    tax_amount = from_minor_units(
                        total_details.get("amount_tax"), currency
                    )

                    # 1. Create the invoice
                    invoice = Invoice.objects.create(
                        invoice_number=build_invoice_number(),
                        user=user,
                        phone=user.mobile,
                        shipping_address=user.address,
                        payment_method="card",
                        payment_status="paid",
                        order_status="confirmed",
                        total_amount=from_minor_units(
                            session.get("amount_total"), currency
                        ),
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

                        product = Product.objects.filter(id=product_id).first()
                        if product is None:
                            # The customer has already been charged, so an
                            # invoice missing a line it was paid for cannot be
                            # allowed to stand: fail the whole handler and let
                            # Stripe retry the event.
                            raise Product.DoesNotExist(
                                f"Product {product_id} not found for invoice "
                                f"{invoice.invoice_number}"
                            )

                        # 2. Create invoice item, leveraging model's save() method to handle stock
                        InvoiceItem.objects.create(
                            invoice=invoice,
                            product=product,
                            quantity=item.quantity,
                            price=from_minor_units(
                                item.price.unit_amount, currency
                            ),
                        )

                    # 3. Recalculate invoice total based on created items
                    invoice.recalc_total()

                    # 4. Remove purchased items from the cart
                    if cart_item_ids_to_delete:
                        CartItem.objects.filter(user=user, id__in=cart_item_ids_to_delete).delete()
                        logger.info(f"Cleared {len(cart_item_ids_to_delete)} items from cart for user {user.email}")

                except Exception:
                    logger.exception(
                        "Error processing checkout for %s", customer_email
                    )
                    # Returning from inside atomic() does not roll back on its
                    # own - without this the half-written invoice was committed.
                    transaction.set_rollback(True)
                    return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.debug("Stripe event %s handled for tenant %s", event_type, tenant_id)

        return Response(status=status.HTTP_200_OK)


class RazorpayWebhookView(APIView):
    permission_classes = [AllowAny]

    def create_invoice_items_from_invoice(self, invoice):
        """
        Settle a paid Razorpay order.

        The lines are written when the order is created (see
        ProductCheckoutSessionView) so that the invoice always reflects what was
        actually ordered and priced. Anything still in the cart that matches a
        purchased product is cleared here.

        Older orders created before the lines were snapshotted still fall back
        to the cart so they are not left empty.
        """
        with transaction.atomic():
            if not invoice.items.exists():
                cart_items = (
                    CartItem.objects.select_related("product")
                    .filter(user=invoice.user)
                    .order_by("product__name")
                )

                if not cart_items.exists():
                    return

                for cart_item in cart_items:
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        product=cart_item.product,
                        quantity=cart_item.quantity,
                        price=cart_item.price,
                    )

            purchased_product_ids = invoice.items.values_list(
                "product_id", flat=True
            )
            CartItem.objects.filter(
                user=invoice.user, product_id__in=list(purchased_product_ids)
            ).delete()

    def post(self, request, tenant_id):
        webhook_signature = request.headers.get('X-Razorpay-Signature', '')

        # Request body must be read as raw bytes for signature validation
        webhook_body = request.body

        logger.info("Received Razorpay webhook for tenant %s", tenant_id)

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

                with transaction.atomic():
                    # Razorpay retries webhooks, so lock the row and re-read the
                    # status inside the transaction to keep the handler
                    # idempotent under concurrent deliveries.
                    invoice = (
                        Invoice.objects.select_for_update()
                        .filter(razorpay_order_id=razorpay_order_id)
                        .first()
                    )

                    if invoice and invoice.payment_status != 'paid':
                        invoice.payment_status = 'paid'
                        invoice.order_status = 'confirmed'
                        invoice.razorpay_payment_id = razorpay_payment_id
                        invoice.save(
                            update_fields=[
                                "payment_status",
                                "order_status",
                                "razorpay_payment_id",
                            ]
                        )

                    if invoice and invoice.payment_status == 'paid':
                        self.create_invoice_items_from_invoice(invoice)

            elif event_type == 'payment.failed':
                failed_entity = data.get('payload', {}).get('payment', {}).get('entity', {})
                razorpay_order_id = failed_entity.get('order_id')

                with transaction.atomic():
                    invoice = (
                        Invoice.objects.select_for_update()
                        .filter(razorpay_order_id=razorpay_order_id)
                        .first()
                    )

                    # Never delete an order that has been paid - a late
                    # payment.failed for a retried attempt used to wipe the
                    # record of a successful purchase.
                    if invoice and invoice.payment_status != 'paid':
                        # Model delete() walks the items, which returns the
                        # reserved stock to the products.
                        invoice.delete()

        return Response(status=status.HTTP_200_OK)



                   

        