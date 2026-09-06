"""
URL configuration for salon_management project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from decouple import config

def health_check(request):
    print("========== HEALTH CHECK ==========")
    hs  = config("ALLOWED_HOSTS", default="localhost",)
    print("ALLOWED_HOSTS:", hs)
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("health/", health_check, name="health"),
    path('admin/', admin.site.urls),
    
    path("api/account/", include("account.urls")),
    path("api/core/", include("core.urls")),
    
    path("api/salon/",include("salonDetails.urls")),
    
    path("api/tenant/", include("tenant.urls")),

    path("api/subscription/",include("subscription.urls")),
    path("api/checkout/",include("checkout.urls")),
    path("api/webhook-handler/", include("webhook_handler.urls")),

    path("api/appointment/", include("appointment.urls")),

    path("api/product-sales/", include("product_sales.urls")),
    path("api/stock-management/", include("stock_management.urls")),

    path("api/payments/", include("payments.urls")),

    path("api/stripe/", include("djstripe.urls", namespace="djstripe")),
]
