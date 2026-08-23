
from djstripe.models import Price
from django.conf import settings

import logging
import stripe

logger = logging.getLogger(__name__)


def find_plan_by_price(price_id, active_only=True):
    """
    Look up a SubscriptionPlan from whichever price identifier the caller sent.

    ``SubscriptionPlan.stripe_price_id`` is djstripe's internal integer key, but
    clients naturally hold the Stripe price string ("price_123"). Filtering the
    integer column with a string raises ValueError - a 500 - so both forms are
    accepted here and anything unrecognised simply returns None.
    """
    from subscription.models import SubscriptionPlan

    if not price_id:
        return None

    queryset = SubscriptionPlan.objects.all()
    if active_only:
        queryset = queryset.filter(is_active=True)

    price_id = str(price_id)

    if price_id.isdigit():
        return queryset.filter(stripe_price_id=int(price_id)).first()

    return queryset.filter(stripe_price__id=price_id).first()


def resolve_stripe_price(price_id):
    """The djstripe Price row for either identifier form, or None."""
    if not price_id:
        return None

    price_id = str(price_id)

    if price_id.isdigit():
        return Price.objects.filter(djstripe_id=int(price_id)).first()

    return Price.objects.filter(id=price_id).first()


def get_active_subscription(stripe_customer_id, tenant):

    stripe.api_key = settings.STRIPE_SECRET_KEY

    if not stripe_customer_id:
        return None

    try:
        active_subscriptions = stripe.Subscription.list(
            customer=stripe_customer_id, status="active"
        )

        if active_subscriptions["data"]:
            # Field is stripe_subscription_id. The old "stipe_..." spelling just
            # set a stray attribute, so the id was never written to the row.
            tenant.stripe_subscription_id = active_subscriptions.data[0].id
            tenant.save(update_fields=["stripe_subscription_id"])

    except Exception:
        logger.exception(
            "Could not list Stripe subscriptions for customer %s",
            stripe_customer_id,
        )
        active_subscriptions = None

    return active_subscriptions

def cancel_subscriptions(stripe_subscription_id, period_end=None):
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        if period_end:
            stripe.Subscription.modify(
                stripe_subscription_id, cancel_at_period_end=True
            )
        else:
            stripe.Subscription.delete(stripe_subscription_id)
        return True
    except Exception:
        logger.exception(
            "Could not cancel Stripe subscription %s", stripe_subscription_id
        )
        return False
    
def  upgrade_subscription(sub_id, price_id, customer_id, tenant, prev_plan_id, upgrade_plan_id, user_id):
    
    stripe.api_key = settings.STRIPE_SECRET_KEY

    price = resolve_stripe_price(price_id)
    if price is None:
        logger.error("No local Price row for price_id=%s", price_id)
        return None

    try:
        new_subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price":price.id}],
            metadata={
                "type":"upgrade_subscriptions",
                "previous_subscription_id": sub_id,
            },
            collection_method="charge_automatically",
            payment_behavior="default_incomplete",
        )

        latest_invoice = stripe.Invoice.retrieve(
            new_subscription.latest_invoice
        )

        latest_invoice = stripe.Invoice.modify(
            latest_invoice.id,
            metadata={
                "type": "upgrade_subscriptions",
                "user_id": user_id,
                "previous_subscription_id": sub_id,
                "new_subscription_id": new_subscription.id,
                "schema_name": tenant.schema_name,
                "prev_plan_id": prev_plan_id,
                "upgrade_plan_id": upgrade_plan_id,
            },
        )

        # If there's a PaymentIntent associated with the latest invoice
        if latest_invoice.amount_due != latest_invoice.amount_paid:
            return latest_invoice.hosted_invoice_url

        return None

    except stripe.error.StripeError:
        logger.exception("Could not create upgrade subscription for %s", customer_id)
        return None

