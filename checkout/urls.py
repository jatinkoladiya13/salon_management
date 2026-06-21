from django.urls import path, include

from .views import *

urlpatterns = [
   
    path("create-checkout-session/", CheckoutSessionview.as_view(), name="create-checkout-session"),

]
