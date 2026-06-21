from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()

router.register("subscription_plan", SubscriptionPlanManageView)
router.register("invoice", InvoiceViewSet)

urlpatterns = [
    path("stripe-product-list/", StripeProductListAPIView.as_view(), name="stripe-product-list"),

    path("get-own-subscription/", GetOwnSubscription.as_view(), name="get-own-subscription"), 
    path("cancel-subscription/",CancelSubscription.as_view(), name="cancel-subscription"),
    path("upgrade-subscription/", UpgradeSubscriptionPlan.as_view(), name="upgrade-subscription"),
    
    path("", include(router.urls)),
]
