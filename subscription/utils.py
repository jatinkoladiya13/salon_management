
from djstripe.models import Price
from django.conf import settings

import stripe

def get_active_subscription(stripe_customer_id, tenant):

    stripe.api_key = settings.STRIPE_SECRET_KEY
    
    try:
        active_subscriptions = stripe.Subscription.list(
            customer=stripe_customer_id,status="active"   
        )

        if active_subscriptions["data"]:
            stipe_subscription_id = active_subscriptions.data[0].id
            tenant.stipe_subscription_id = stipe_subscription_id
            tenant.save()

    except Exception as e:
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
    except Exception as e:
        print("Error canceling subscription", e)
        return False
    
def  upgrade_subscription(sub_id, price_id, customer_id, tenant, prev_plan_id, upgrade_plan_id, user_id):
    
    stripe.api_key = settings.STRIPE_SECRET_KEY

    price = Price.objects.get(djstripe_id=price_id)

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
        
    except stripe.error.StripeError as e:
        print("Error:", e)
        return None

