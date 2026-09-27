from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StripeWebhookView, StripeProductWebhookView, RazorpayWebhookView

urlpatterns = [
    path("stripe/", StripeWebhookView.as_view(), name="stripe_webhook"),
    path("stripe-product-webhook/<uuid:tenant_id>/", StripeProductWebhookView.as_view(), name="stripe_product_webhook"),

    path("razorpay/<uuid:tenant_id>/", RazorpayWebhookView.as_view(), name="razorpay_webhook"),
]
