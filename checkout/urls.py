from django.urls import path, include
from rest_framework import routers
from .views import *

router = routers.SimpleRouter()

router.register(r"confirmation", CallBackViewSet, basename="confirmation")

urlpatterns = [
    # path("", include(router.urls))
    path("buy-credit/", BuyCreditView.as_view(), name= "buy-credit"),
    path("create-checkout-session/", CheckoutSessionView.as_view(), name="create-checkout-session"),
]
