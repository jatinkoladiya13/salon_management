from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()

router.register("subscription_plan", SubscriptionPlanManageView)
# Explicit basename: without it this route is also named "invoice-list", which
# collides with product_sales' order invoices and makes reverse() resolve to
# whichever URLconf was loaded last.
router.register("invoice", InvoiceViewSet, basename="subscription-invoice")

urlpatterns = [
    path("stripe-product-list/", StripeProductListAPIView.as_view(), name="stripe-product-list"),

    path("get-own-subscription/", GetOwnSubscription.as_view(), name="get-own-subscription"), 
    path("cancel-subscription/",CancelSubscription.as_view(), name="cancel-subscription"),
    path("upgrade-subscription/", UpgradeSubscriptionPlan.as_view(), name="upgrade-subscription"),
    
    path("", include(router.urls)),
]
