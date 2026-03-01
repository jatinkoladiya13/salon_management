from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StripeWebhookView

urlpatterns = [
    path("stripe/", StripeWebhookView.as_view(), name="stripe_webhook"),
]
