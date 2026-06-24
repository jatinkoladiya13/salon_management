from django.conf import settings

from rest_framework.views import Response, APIView
from rest_framework import permissions, status

from subscription.models import SubscriptionPlan
from tenant.models import Tenant

from utils.permissions import IsAdmin
import utils.response_handler as rh 

from decouple import config
from uuid import uuid4

import stripe
import datetime

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


 

