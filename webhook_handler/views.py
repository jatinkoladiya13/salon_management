from django.conf import settings
from datetime import timedelta
from django.utils import timezone

from djstripe.models import Price

from rest_framework.views import Response, APIView
from rest_framework.permissions import AllowAny
from rest_framework import status

from subscription.models import SubscriptionPlan
from tenant.models import Tenant

import logging
import stripe


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