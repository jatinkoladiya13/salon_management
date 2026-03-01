from rest_framework.views import APIView, Response
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

from django.conf import settings
from djstripe.models import Price

from checkout.serializers import BuyCreditSerializer

from tenant.models import Tenant
from core.constants import MANAGE_SUBSCRIPTION
from subscription.models import SubscriptionPlan
import utils.response_handler as rh
from utils.permissions import CustomPermission
from utils.custom_exception import BadRequestException
from account.models import User
from decouple import config
from uuid import uuid4

import datetime
import stripe
# Create your views here.

def get_stripe_customer_id(tenant, user):
    customer_org = Tenant.objects.get(schema_name=tenant.schema_name).salonDetails

    if tenant.stripe_customer_id is not None:
        # Customer already exists on Stripe
        stripe_customer_id = tenant.stripe_customer_id
    else:
        # billing_address = Address
        organization_email = customer_org.organization_email
        stripe_customer = stripe.Customer.create(
            name= customer_org.name,
            email= organization_email
            if organization_email else user.email,
        )
        
        tenant.stripe_customer_id = stripe_customer.id
        tenant.save()
        stripe_customer_id = stripe_customer.id
        
    return stripe_customer_id


class BuyCreditView(APIView):
    permission_classes = [
        IsAuthenticated,
        CustomPermission(MANAGE_SUBSCRIPTION)
    ]

    def post(self, request):
        address = True
        serializer = BuyCreditSerializer(data=request.data)

        if not serializer.is_valid():
            response = rh.ResponseMsg(
                {},
                True,
                serializer.errors,
            )
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data=response.response
            )
        
        price_id = serializer.validated_data.get("price_id")
        quantity = serializer.validated_data.get("quantity")
        
        credit_plan = SubscriptionPlan.objects.get(id=price_id)
        price  = credit_plan.stripe_price

        stripe.api_key = settings.STRIPE_TEST_SECRET_KEY
        tenant = Tenant.objects.get(schema_name=request.tenant.schema_name)
        
        if tenant.subscription_status in ["expired"]:
            response = rh.ResponseMsg( 
                {},
                True,
                "No active subscription found, please subscribe to a plan",
            )
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data=response.response
            )
        
        stripe_customer_id = get_stripe_customer_id(tenant, request.user)

        if not stripe_customer_id:
            response = rh.ResponseMsg(
                {"address": address},
                False,
                "Checkout session created successfully!!!",
            )
            return Response(status=status.HTTP_200_OK, data=response.response)
        
        #generate a uuid4
        uid = uuid4()
        
        session_data ={
            "type": "extra_credit_plan",
            "uid": uid,
            "schema_name": request.tenant.schema_name,
            "organisation_id": tenant.salonDetails_id,
            "user_id": request.user.id,
            "plan_id": credit_plan.id,
            "quantity": quantity,
        } 
        
        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types = ["card"],
                line_items = [
                    {
                        "price": price.id,  # Stripe ID of the Price object
                        "quantity": quantity,
                    }
                ],
                mode="payment",
                success_url=f'{config("HTTP_PROXY")}{request.tenant.schema_name}.{config("HOST_URI")}/payment-confirmation/success',
                cancel_url=f'{config("HTTP_PROXY")}{request.tenant.schema_name}.{config("HOST_URI")}/payment-confirmation/failed',
                customer=stripe_customer_id,
                metadata=session_data,
                allow_promotion_codes=True,
            )
        except Exception as error:
            response = rh.ResponseMsg(
                {},
                True,
                error,
            )
            return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)

        response = rh.ResponseMsg(
            {"checkout_url": checkout_session.url, "address": address},
            False,
            "Checkout session created successfully!!!",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    
class CheckoutSessionView(APIView):
    permission_classes = [
        IsAuthenticated,
        CustomPermission(MANAGE_SUBSCRIPTION)
    ]    

    def post(self, request):
        """
        Create a new checkout subscriptions session
        """

        address = True

        if(request.tenant.subscription_status == "active"  and request.tenant.subscription_plan.interval != "trial"):
            response = rh.ResponseMsg(
                {},
                True,
                "Subscription already active, you can only upgrade or downgrade your subscription plan",
            )
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data=response.response
            )
        
        price_id = request.data.get("price_id")

        subscription_plan =  SubscriptionPlan.objects.get(
           stripe_price_id=price_id
        )

        if not price_id:
            response = rh.ResponseMsg(
                {},
                True,
                "Price ID is required in the request body",
            )
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data=response.response
            )
        
        price = Price.objects.id(
            stripe_id=price_id
        )

        stripe.api_key = settings.STRIPE_TEST_SECRET_KEY

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
        
        #generate a uuid4
        uid = uuid4()

        session_data = {
            "type": "new_subscription",
            "uid": uid,
            "schema_name": request.tenant.schema_name,
            "organisation_id": tenant.salonDetails_id,
            "user_id": request.user.id,
        }
        
        expiration_time = int(
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
            expires_at=expiration_time,
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

class CallBackViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    def buy_credit_success(self, request, uid=None):
        if not uid:
            # response = rh.ResponseMsg(
            #     {},
            #     True,
            #     "session_id is required in the request url",
            # )
            # return Response(
            #     status=status.HTTP_400_BAD_REQUEST, data=response.response
            # )
            raise BadRequestException
        # payment_session = PaymentSession.objects.get(uid=uid)

    #     if payment_session.paid:
    #         response = rh.ResponseMsg(
    #             {"message": "Payment successful"},
    #             False,
    #             "Payment successful",
    #         )
    #         return Response(status=status.HTTP_200_OK, data=response.response)

    #     # set payment session to paid
    #     payment_session.paid = True
    #     payment_session.save()

    #     # add call credit to the tenant
    #     credit_seconds = (
    #         payment_session.quantity
    #         * payment_session.price.transform_quantity["divide_by"]
    #         * 60
    #     )
    #     tenant = payment_session.tenant
    #     tenant.call_credits_in_sec += credit_seconds
    #     tenant.credit_update_timestamp = datetime.datetime.now(
    #         datetime.timezone.utc
    #     )
    #     tenant.save()

    #     response = rh.ResponseMsg(
    #         {"message": "Payment successful"},
    #         False,
    #         "Payment successful",
    #     )
    #     return Response(status=status.HTTP_200_OK, data=response.response)
    
    # def check_subscription_success(self, request, uid=None):
    #     if not uid:
    #         raise BadRequestException(
    #             "Session id is required in the request url"
    #         )

    #     payment_session = PaymentSession.objects.get(uid=uid)

        # if payment_session.paid:
        #     response = rh.ResponseMsg(
        #         {"message": "Payment successful"},
        #         False,
        #         "Payment successful",
        #     )
        #     return Response(status=status.HTTP_200_OK, data=response.response)
        ###
        # add_subscription_features(uid)

        response = rh.ResponseMsg(
            {"message": "Payment successful"},
            False,
            "Payment successful",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)