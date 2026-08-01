from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaymentConfigurationViewSet

router = DefaultRouter()
router.register(r"configurations", PaymentConfigurationViewSet, basename="payment-configuration")

urlpatterns = [
    path("", include(router.urls)),
]