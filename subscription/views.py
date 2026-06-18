from django.shortcuts import render
from django.conf import settings

from rest_framework import viewsets, status, filters, mixins
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from rest_framework.views import Response, APIView
from rest_framework.viewsets import ViewSet
from rest_framework import status

from utils.permissions import IsPublicSchemaSuperUser
from utils.pagination import CustomPageNumberPagination
from subscription.serializers import (
    PriceSerializer, 
    InvoiceSerializer, 
    SubscriptionPlanGetSerializer, 
    SubscriptionPlanCreateUpdateSerializer,
    SubscriptionPlanTypeGETSerializer,
    SubscriptionPlanTypeCreateUpdateSerializer
)
# from call_credit.models import CallCredit
from core.constants import MANAGE_SUBSCRIPTION
from utils.permissions import CustomPermission
from utils.custom_exception import BadRequestException
from djstripe.models import Price, Invoice
from .models import *
import utils.response_handler as rh
import datetime
import stripe

# Create your views here.

def get_active_subscription(stripe_customer_id, tenant):

    stripe.api_key = settings.STRIPE_TEST_SECRET_KEY
    
    try:
        print("this is working on get active subscription")
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
    stripe.api_key = settings.STRIPE_TEST_SECRET_KEY

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
    
    stripe.api_key = settings.STRIPE_TEST_SECRET_KEY

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

class SubscriptionViewSet(ViewSet):

    permission_classes = [
        IsAuthenticated,
        CustomPermission(MANAGE_SUBSCRIPTION)
    ]

    def list(self,request):
        tenant = request.tenant
        subscription_plan = tenant.subscription_plan

        data  = {
            "plan_status": tenant.subscription_status,
            "trial_completed": tenant.trial_completed,
            "next_invoice": (
                tenant.subscription_end_date
                if subscription_plan and subscription_plan.interval != "trial"
                else None
            ),
            # "available_credit_min": CallCredit.current_subscription_available_min()
            # // 60,
            # "extra_credit_min": (
            #     CallCredit.available_credits()
            #     - CallCredit.current_subscription_available_min()
            # )
            # // 60,
            "subscription_plan": {
                "name": subscription_plan.name,
                "description": subscription_plan.description,
                "interval": subscription_plan.interval,
                "plan_credit_min": subscription_plan.credits_minutes,
                "days_left_to_expire": (
                    tenant.subscription_end_date - datetime.date.today()
                ).days,
            },
        }

        response = rh.ResponseMsg(
            data,
            False,
            "Subscription data get successfully!!!",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    

    @action(detail=False, methods=["get"], url_path="call-credits")
    def view_call_credits(self, request):
        tenant  = request.tenant

        response = rh.ResponseMsg(
            {
                # "call_credits":CallCredit.available_credits(),
                # "credis_credits":CallCredit.all_call_credits().values(
                #     "credit_type","credits_sec", "expiry_date"
                # )
            },
            False,
            "Call credits fetched successfully"
        )

        return Response(data=response.response, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path="call-credit-pricing")
    def call_credit_pricing(self,request):
        tenant= request.tenant
        subscription_plan = tenant.subscription_plan

        today_utc_data =  datetime.datetime.utcnow()
    
        if (
            tenant.trial_end_date  and tenant.trial_end_date < today_utc_data.date()
        ):
            return BadRequestException("Your subscription is expired")
        
        credit_plan = SubscriptionPlan.objects.get(slug=subscription_plan.slug)
        # if "basic" in subscription_plan.slug:
        #     credit_plan = SubscriptionPlan.objects.get(slug="basic_subscription")
        # elif "starter" in subscription_plan.slug:
        #     credit_plan = SubscriptionPlan.objects.get(slug="starter_credits")
        # elif "pro" in subscription_plan.slug:
        #     credit_plan = SubscriptionPlan.objects.get(slug="pro_credits")
        # elif "growth" in subscription_plan.slug:
        #     credit_plan = SubscriptionPlan.objects.get(slug="growth_credits")
        # elif subscription_plan.interval == "trial":
        #     credit_plan = SubscriptionPlan.objects.get(slug="trial_subscription")        

        stripe_price = credit_plan.stripe_price 
        price = (stripe_price.unit_amount / 100 if stripe_price and  stripe_price.unit_amount else 0)

        data = [
            {
                "id":credit_plan.id,
                "price":price ,
                "currency":stripe_price.currency if stripe_price else None,
                "min":credit_plan.credits_minutes,
            }
        ]    

        response = rh.ResponseMsg(
            data,
            False,
            "Call credit pricing fetched successfully",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    
    @action(detail=False, methods=["post"], url_path="cancel-subscription")
    def cancel_subscription(self, request):
        tenant = request.tenant
        subscription_plan = tenant.subscription_plan
        subscription_status = tenant.subscription_status
        stipe_subscription_id = tenant.stipe_subscription_id
        stripe_customer_id = tenant.stripe_customer_id
        
        message = None

        # if subscription plan is trial
        if subscription_plan and subscription_plan.interval == "trial":
            raise BadRequestException(
                "You do not have any active subscription to cancel"
            )
        
        # if subscription is inactive or expired
        if subscription_status in ["inactive", "expired"]:
            raise BadRequestException(
                "You do not have any active subscription to cancel"
            )
        
        if not stipe_subscription_id:
            stripe_active_subscriptions = get_active_subscription(
                stripe_customer_id, tenant
            )
            if stripe_active_subscriptions:
                stipe_subscription_id = stripe_active_subscriptions.data[0].id
        
        if stipe_subscription_id:
            if cancel_subscriptions(stipe_subscription_id, period_end=True):
                tenant.subscription_status = "cancelled"
                tenant.subscription_plan = None
                tenant.stipe_subscription_id = None
                tenant.save()
                message = "Subscription cancelled successfully"
            else:
                raise BadRequestException("Error in cancelling subscription")

        else:
            raise BadRequestException(
                "You do not have any active subscription to cancel"
            )        
        
        response = rh.ResponseMsg(
            {},
            False,
            message,
        )

        return Response(status=status.HTTP_200_OK, data=response.response)
    
    @action(detail=False, methods=["post"], url_path="upgrade-subscriptions")
    def upgrade_subscription(self, request):
        price_id = request.data.get("price_id")
        tenant = request.tenant
        subscription_plan = tenant.subscription_plan
        subscription_status = tenant.subscription_status
        stripe_customer_id = tenant.stripe_customer_id
        upgrade_plan = SubscriptionPlan.objects.get(stripe_price_id=price_id)
        message = None

        # if subscription plan is trial
        if subscription_plan and subscription_plan.interval == "trial":
            raise BadRequestException(
                "You do not have any active subscription to upgrade"
            )
        
        # if subscription is inactive or expired
        if subscription_status in ["inactive", "expired"]:
            raise BadRequestException(
                "You do not have any active subscription to upgrade"
            )

        # id subscription is inactive  or expired
        if subscription_plan and subscription_plan.interval != "trial":
            if not upgrade_plan:
                print("Invalid price id")
                raise BadRequestException
            elif upgrade_plan.interval  != subscription_plan.interval:
                raise BadRequestException(
                    "You can only upgrade to a plan with the same interval"
                )
            elif upgrade_plan.id == subscription_plan.id:
                raise BadRequestException(
                    "You already have same subscriptions"
                )
            
        print("this is working now")
        # check if there is active subscription for this customer
        if message is None:
            stripe_active_subscriptions = get_active_subscription(
                stripe_customer_id, tenant
            )

            if stripe_active_subscriptions["data"]:
                stripe_active_subscriptions = (
                    stripe_active_subscriptions.to_dict()
                )
                stipe_subscription_id = stripe_active_subscriptions["data"][
                    0
                ].id
                inv_url = upgrade_subscription(
                    stipe_subscription_id,
                    price_id,
                    stripe_customer_id,
                    tenant,
                    subscription_plan.id,
                    upgrade_plan.id,
                    request.user.id,
                )
                
                if inv_url:
                    response = rh.ResponseMsg(
                        {"url": inv_url},
                        False,
                        "Pay the invoice to upgrade or downgrade the plan",
                    )
                    return Response(
                        status=status.HTTP_200_OK, data=response.response
                    )
            else:
                raise BadRequestException(
                    "You do not have any active subscription to upgrade"
                )


class StripePricePlanManageView(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Price.objects.all()
    serializer_class = PriceSerializer
    pagination_class = CustomPageNumberPagination
    permission_classes = [IsPublicSchemaSuperUser]
    filter_backends = [filters.SearchFilter]
    search_fields = ["human_readable_price"]


    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            serializer.data,
            False,
            "All Price Plans data get Successfully!!!",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    
class InvoiceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, CustomPermission(MANAGE_SUBSCRIPTION)]
    pagination_class = CustomPageNumberPagination
    serializer_class = InvoiceSerializer
    queryset = Invoice.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant = self.request.tenant
        stripe_customer_id = tenant.stripe_customer_id

        # Apply stripe customer and paid filter
        queryset = queryset.filter(
            customer_id=stripe_customer_id, status="paid"
        )

        # Get start_date and end_date from request query params
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")

        if start_date and end_date:
            start_date = datetime.datetime.strptime(
                start_date, "%Y-%m-%d"
            ).date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            # Default to the last one year
            end_date = timezone.now().astimezone(timezone.utc).date()
            start_date = end_date - datetime.timedelta(days=365)

        # Apply date range filter
        queryset = queryset.filter(created__date__range=[start_date, end_date])

        return queryset
    
    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            serializer.data,
            False,
            "All invoice fetched successfully",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)

class  CheckSubscriptions(APIView):

    def get(self,  request):
        tenant  = request.tenant
        subscription_end_date = tenant.subscription_end_date
        subscription_Status = tenant.subscription_status
        today_utc_date =    datetime.datetime.utcnow().date()

        if subscription_end_date and subscription_end_date < today_utc_date:
            tenant.subscription_status = "expired"
            tenant.save()
            response = rh.ResponseMsg(
                {},
                False,
                "Your subscription is expired",
            )
            return Response(status=status.HTTP_200_OK, data=response.response)
        
        else:
            response = rh.ResponseMsg(
                {},
                False,
                "Your subscription is active",
            )
            return Response(status=status.HTTP_204_NO_CONTENT, data=response.response)


class SubscriptionPlanManageView(viewsets.ModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanGetSerializer
    permission_classes = [IsPublicSchemaSuperUser]
    filter_backends = [filters.SearchFilter]
    pagination_class = CustomPageNumberPagination
    search_fields = ["name", "slug"]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            self.serializer_class = SubscriptionPlanCreateUpdateSerializer
        return super().get_serializer_class()
    
    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            serializer.data,
            False,
            "All Subscription Plans data get Successfully!!!"
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    
    def retrieve(self, request, *args, **kwargs):
        serializer =  super().retrieve(request, *args, **kwargs)
        response = rh.ResponseMsg(
            serializer.data,
            False,
            "Subscription Plan data retrieve Successfully!!!"
        )
        return Response(status=status.HTTP_200_OK,  data=response.response)
    
    def create(self, request, *args, **kwargs):
        serializer = super().create(request, *args, **kwargs)
        response = rh.ResponseMsg(
            serializer.data,
            False,
            "Subscription Plan created Successfully!!!",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    
    def update(self, request, *args, **kwargs):
        serializer = super().update(request, *args, **kwargs)
        response = rh.ResponseMsg(
            serializer.data,
            False,
            "Subscription Plan updated Successfully!!!"
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    
    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg(
            {},
            False,
            "Subscription Plan deleted Successfully!!!",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    
class SubscriptionPlanTypeManageView(viewsets.ModelViewSet):
    pass
    # queryset = SubscriptionPlanType.objects.all()
    # serializer_class = SubscriptionPlanTypeGETSerializer
    # permission_classes = [IsPublicSchemaSuperUser]
    # filter_backends = [filters.SearchFilter]
    # pagination_class = CustomPageNumberPagination
    # search_fields = ["plan_type"]

    # def get_serializer_class(self):
    #     if self.action in ["create", "update", "partial_update"]:
    #         self.serializer_class = SubscriptionPlanTypeCreateUpdateSerializer
    #     return super().get_serializer_class()

    # def list(self, request, *args, **kwargs):
    #     serializer = super().list(request, *args, **kwargs)
    #     response = rh.ResponseMsg(
    #         serializer.data,
    #         False,
    #         "All Subscription Plans Type data get Successfully!!!",
    #     )
    #     return Response(status=status.HTTP_200_OK, data=response.response)

    # def retrieve(self, request, *args, **kwargs):
    #     serializer = super().retrieve(request, *args, **kwargs)
    #     response = rh.ResponseMsg(
    #         serializer.data,
    #         False,
    #         "Subscription Plan Type data retrieve Successfully!!!",
    #     )
    #     return Response(status=status.HTTP_200_OK, data=response.response)

    # def create(self, request, *args, **kwargs):
    #     serializer = super().create(request, *args, **kwargs)
    #     response = rh.ResponseMsg(
    #         serializer.data,
    #         False,
    #         "Subscription Plan Type created Successfully!!!",
    #     )
    #     return Response(status=status.HTTP_200_OK, data=response.response)

    # def update(self, request, *args, **kwargs):
    #     serializer = super().update(request, *args, **kwargs)
    #     response = rh.ResponseMsg(
    #         serializer.data,
    #         False,
    #         "Subscription Plan Type updated Successfully!!!",
    #     )
    #     return Response(status=status.HTTP_200_OK, data=response.response)

    # def destroy(self, request, *args, **kwargs):
    #     super().destroy(request, *args, **kwargs)
    #     response = rh.ResponseMsg(
    #         {},
    #         False,
    #         "Subscription Plan Type deleted Successfully!!!",
    #     )
    #     return Response(status=status.HTTP_200_OK, data=response.response) 