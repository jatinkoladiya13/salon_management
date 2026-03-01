from django_tenants.utils import schema_context
from django.shortcuts import render
from django.conf import settings

from rest_framework.views import Response, APIView
from rest_framework.permissions import AllowAny
from rest_framework import status

from djstripe.models import Price

from subscription.models import SubscriptionPlan
from subscription.views import cancel_subscriptions
from call_credit.models import CallCredit
from tenant.models import Tenant

from datetime import datetime, timedelta

import logging
import stripe
# Create your views here.

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_TEST_SECRET_KEY

class StripeWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        payload  = request.body
        sig_header = request.headers.get('STRIPE_SIGNATURE')
        endpoint_secret = settings.DJSTRIPE_WEBHOOK_SECRET

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)

            print(f"Event:----{event}===Event_type--------{event["type"]}")

            if event["type"] == "checkout.session.completed":
                session_data = event.data["object"]
                metadata  = session_data.get("metadata", {})

                if session_data.get("payment_status") == "paid":
                    if metadata.get("type") == "extra_credit_plan":
                        plan_id = metadata["plan_id"]
                        quantity = int(metadata["quantity"])
                        schema_name = metadata["schema_name"]

                        try:
                            credit_plan = SubscriptionPlan.objects.get(id = plan_id)
                            validity_days = 365 if credit_plan.interval == "yearly" else 30
                            validity_date = datetime.utcnow().date() + timedelta(days=validity_days)
                            
                            with schema_context(schema_name):
                                CallCredit.add_call_credits(
                                    quantity * credit_plan.credits_minutes * 60,
                                    "extra_credit",
                                    validity_date
                                )
                            logger.info("Extra credits added to tenant: %s", schema_name)    
                             
                        except Exception as e:
                            logger.error("Error processing extra credit plan: %s", str(e))    
            
            elif event["type"] == "invoice.payment_succeeded":
                inv_data = event.data["object"]
                metadata = inv_data.get("metadata", {})
                today_utc = datetime.utcnow()

                def get_next_date(interval):
                    if interval == "monthly":
                        return today_utc + timedelta(days=30)
                    return today_utc + timedelta(days=365)
                
                if metadata and metadata.get("type") == "upgrade_subscriptions":
                    schema_name = metadata["schema_name"]
                    upgrade_plan_id = metadata["upgrade_plan_id"]
                    new_subscription_id =  metadata["new_subscription_id"]
                    previous_subscription_id = metadata["previous_subscription_id"]

                    tenant  = Tenant.objects.get(schema_name=schema_name)
                    upgraded_plan = SubscriptionPlan.objects.get(id=upgrade_plan_id)

                    expiry_date = get_next_date(upgraded_plan.interval)
                    tenant.subscription_plan = upgraded_plan
                    tenant.subscription_end_date = expiry_date
                    tenant.stipe_subscription_id = new_subscription_id
                    tenant.credit_exhausted = False
                    tenant.save()

                    with schema_context(schema_name):
                        CallCredit.add_call_credits(
                            upgraded_plan.credits_minutes * 60,
                            "subscription",
                            expiry_date
                        )

                    cancel_subscriptions(previous_subscription_id)
                    logger.info("Subscription upgraded for tenant: %s", schema_name)

                elif not metadata:
                    billing_reason = inv_data.get("billing_reason")
                    if billing_reason in ["subscription_create", "subscription_cycle"]:
                        try:
                            price_id = inv_data["lines"]["data"][0]["pricing"]["price_details"]["price"]
                            stripe_price = Price.objects.get(id=price_id)
                            subscription_plan = SubscriptionPlan.objects.get(stripe_price=stripe_price)
                            tenant = Tenant.objects.get(stripe_customer_id=inv_data["customer"])

                            expiry_date = get_next_date(subscription_plan.interval)

                            tenant.subscription_plan = subscription_plan
                            tenant.subscription_status = "active"
                            tenant.subscription_end_date = expiry_date
                            tenant.stipe_subscription_id = inv_data["parent"]["subscription_details"]["subscription"]
                            tenant.credit_exhausted = False
                            tenant.save()

                            with schema_context(tenant.schema_name):
                                CallCredit.add_call_credits(
                                    subscription_plan.credits_minutes * 60,
                                    "subscription",
                                    expiry_date
                                )

                            logger.info("Subscription created or renewed for tenant: %s", tenant.schema_name)
                        except Exception as e:
                            logger.error("Error processing subscription payment: %s", str(e))
            
            elif event["type"] == "cancel_subscription_handler":
                data = event.data["object"]
                customer_id = data["customer"]
                subscription_id = data["subscription"]
                try:
                    tenant = Tenant.objects.get(stripe_customer_id=customer_id)
                    if tenant.stripe_customer_id == subscription_id:
                        tenant.subscription_status = "cancelled"
                        tenant.subscription_plan = None
                        tenant.stipe_subscription_id = None
                        tenant.save()
                        logger.info("Subscription cancelled for tenant: %s", tenant.schema_name)
                except Tenant.DoesNotExist:
                    logger.warning("Tenant not found for customer_id: %s", customer_id)

        except ValueError as e:
            logger.error("Invalid payload: %s", str(e))
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            logger.error("Invalid signature: %s", str(e))
            return Response(status=status.HTTP_400_BAD_REQUEST)
 
        # You can optionally manually handle event types here if needed
        logger.info("Received Stripe webhook: %s", event['type'])

        return Response(status=status.HTTP_200_OK)
