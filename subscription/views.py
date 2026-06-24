from django.conf import settings

from rest_framework import viewsets, status, filters, mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.views import Response, APIView
from rest_framework import status

from subscription.serializers import (
    ProductSerializer, 
    InvoiceSerializer, 
    SubscriptionPlanGetSerializer, 
    SubscriptionPlanCreateUpdateSerializer,
)


from djstripe.models import Product, Price, Invoice
from tenant.serializers import TeantSerializer
from djstripe.models import Customer
from .models import *

from utils.permissions import CustomPermission, IsPublicSchemaSuperUser, IsAdmin
from utils.pagination import CustomPageNumberPagination
from utils.custom_exception import BadRequestException
from utils.permissions import IsPublicSchemaSuperUser
from .utils import get_active_subscription, cancel_subscriptions, upgrade_subscription
import utils.response_handler as rh
import datetime
import stripe

# Create your views here.

class StripeProductListAPIView(APIView):
    permission_classes = [IsPublicSchemaSuperUser]

    def get(self, request, *args, **kwargs):
        
        # Sync the product and price from stripe dashboard
        stripe.api_key = settings.STRIPE_SECRET_KEY

        products = stripe.Product.list(
            active=True,
            limit=100
        )

        for product in products.auto_paging_iter():
            Product.sync_from_stripe_data(product)

        prices = stripe.Price.list(
            active=True,
            limit=100
        )

        for price in prices.auto_paging_iter():
            Price.sync_from_stripe_data(price)

        products = Product.objects.filter(
            active=True
        ).order_by("name")

        serializer = ProductSerializer(
            products,
            many=True
        )
        response = rh.ResponseMsg(
            serializer.data,
            False   ,
            "All Product with price data get Successfully!!!",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    

class SubscriptionPlanManageView(viewsets.ModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanGetSerializer
    permission_classes = [IsPublicSchemaSuperUser]
    filter_backends = [filters.SearchFilter]
    pagination_class = CustomPageNumberPagination
    search_fields = ["name", "slug"]

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(is_active=True)

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
    

class GetOwnSubscription(APIView):
    permission_classes   = [IsAuthenticated]

    def get(self, request):
        tenant = request.tenant
        subscription_plan = tenant.subscription_plan

        serializer_data = TeantSerializer(tenant)

        response = rh.ResponseMsg(
            serializer_data.data,
            False,
            "Subscription data get Successfully!!!",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)


class CancelSubscription(APIView):
    
    permission_classes =[IsAdmin]

    def get(self, request):

        tenant = request.tenant
        subscription_plan = tenant.subscription_plan
        subscription_status = tenant.subscription_status
        stipe_subscription_id = tenant.stripe_subscription_id
        stripe_customer_id = tenant.stripe_customer_id

        message = None

        if request.tenant.schema_name == "public":
            response = rh.ResponseMsg(
                {},
                True,
                "This operation is not allowed on the public schema."
            )
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data=response.response
            )
       
        # if subscription plan is trial
        if subscription_plan and subscription_plan.interval == "trial":
            response = rh.ResponseMsg(
                {},
                True,
                "You do not have any active subscription to cancel"
            )
            return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)
            
        # if subscription is inactive or expired
        if subscription_status in ["inactive", "expired"]:
            response = rh.ResponseMsg(
                {},
                True,
                "You do not have any active subscription to cancel"
            )
            return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)

        # Check if there is active subscription for this customer
        if not stipe_subscription_id:
            stripe_active_subscriptions = get_active_subscription(
                stripe_customer_id, tenant
            )
            if stripe_active_subscriptions:
                stipe_subscription_id = stripe_active_subscriptions.data[0].id
        # cancel subscription
        if stipe_subscription_id:
            if cancel_subscriptions(stipe_subscription_id, period_end=True):
                # tenant.subscription_status = "cancelled"
                # tenant.subscription_plan = None
                # tenant.stripe_subscription_id = None
                # tenant.save()
                message = "Subscription cancelled successfully"
            else:
                raise BadRequestException("Error in cancelling subscription")
        else:
            response = rh.ResponseMsg(
                {},
                True,
                "You do not have any active subscription to cancel"
            )
            return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)

        response = rh.ResponseMsg(
            {},
            False,
            message,
        )
        return Response(status=status.HTTP_200_OK, data=response.response)


class UpgradeSubscriptionPlan(APIView):
    
    permission_classes =[IsAdmin]

    def post(self, request):

        price_id = request.data.get("price_id")

        if not price_id:      
            response = rh.ResponseMsg(
                {},
                True,
                "You do not have any active subscription to cancel"
            )
            return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)

        tenant = request.tenant
        subscription_plan = tenant.subscription_plan
        subscription_status = tenant.subscription_status
        stipe_subscription_id = tenant.stripe_subscription_id
        stripe_customer_id = tenant.stripe_customer_id

        upgrade_plan = SubscriptionPlan.objects.get(stripe_price_id=price_id)
        message = None

        message = None
       
        # if subscription plan is trial
        if subscription_plan and subscription_plan.interval == "trial":
            response = rh.ResponseMsg(
                {},
                True,
                "You do not have any active subscription to upgrade"
            )
            return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)
            
        # if subscription is inactive or expired
        if subscription_status in ["inactive", "expired"]:
            response = rh.ResponseMsg(
                {},
                True,
                "You do not have any active subscription to upgrade"
            )
            return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)

        if subscription_plan and subscription_plan.interval != "trial":
            if not upgrade_plan:
                raise BadRequestException
            elif upgrade_plan.interval != subscription_plan.interval:
                response = rh.ResponseMsg(
                    {},
                    True,
                    "You can only upgrade to a plan with the same interval"
                )
                return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)
                    
            elif upgrade_plan.id == subscription_plan.id:
                response = rh.ResponseMsg(
                    {},
                    True,
                    "You already have same subscriptions"
                )
                return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)
            
        # Check if there is active subscription for this customer
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
                response = rh.ResponseMsg(
                    {},
                    True,
                    "You do not have any active subscription to upgrade"
                )
                return Response(status=status.HTTP_400_BAD_REQUEST, data=response.response)
    
class InvoiceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAdmin]
    pagination_class = CustomPageNumberPagination
    serializer_class = InvoiceSerializer
    queryset = Invoice.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()

        invoices = stripe.Invoice.list(
            limit=100
        )
    
        for invoice in invoices.auto_paging_iter():
            Invoice.sync_from_stripe_data(invoice)
        
        tenant = self.request.tenant
        stripe_customer_id = tenant.stripe_customer_id
        schema_name = tenant.schema_name
        
        if schema_name == "public":
           
            stripe_customer_id = self.request.query_params.get("stripe_customer_id")
            if stripe_customer_id:
                queryset = queryset.filter(
                    customer=stripe_customer_id
                )
           
            customer_email = self.request.query_params.get("customer_email")
            if customer_email:
                customer_ids = Customer.objects.filter(
                    email=customer_email
                ).values_list("id", flat=True)
                queryset = queryset.filter(
                    customer_id__in=customer_ids
                )

        # Date filtering
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")

        if start_date and end_date:
            start_date = datetime.datetime.strptime(
                start_date, "%Y-%m-%d"
            ).date()

            end_date = datetime.datetime.strptime(
                end_date, "%Y-%m-%d"
            ).date()

            queryset = queryset.filter(
                created__date__range=[start_date, end_date]
            )    
                

            return queryset
    
        queryset = queryset.filter(
            customer=stripe_customer_id
        )

        return queryset

  
    def list(self, request, *args, **kwargs):
        serializer = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            serializer.data,
            False,
            "All invoice fetched successfully",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)        