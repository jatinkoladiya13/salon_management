from django.urls import path, include

from .views import *

urlpatterns = [
   
    path("create-checkout-session/", CheckoutSessionview.as_view(), name="create-checkout-session"),
    path("product-checkout-session/", ProductCheckoutSessionView.as_view(), name="product-checkout-session"),

    path("verify-razorpay-payment/", VerifyRazorpayPaymentView.as_view(), name="verify-razorpay-payment"), 
]
