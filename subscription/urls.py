from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()

router.register(r"mysubscriptions", SubscriptionViewSet, basename="mysubscriptions")

router.register("stripe_price_plan", StripePricePlanManageView)
router.register("invoice", InvoiceViewSet)

router.register("subscription_plan", SubscriptionPlanManageView)
# router.register("subscription_plan_type", SubscriptionPlanTypeManageView)

urlpatterns = [
    path("", include(router.urls)),
    path("check-subscription/", CheckSubscriptions.as_view())
]
