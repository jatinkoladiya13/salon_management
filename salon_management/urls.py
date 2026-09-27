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
from django.conf import settings

def health_check(request):
    # Report the effective settings, not the raw env string: ALLOWED_HOSTS
    # gates the Host header while CHANNELS_ALLOWED_ORIGINS gates the WebSocket
    # Origin header, and confusing the two is what silently kills /ws/ traffic.
    print("========== HEALTH CHECK ==========")
    print("ALLOWED_HOSTS:", settings.ALLOWED_HOSTS)
    print("CHANNELS_ALLOWED_ORIGINS:", settings.CHANNELS_ALLOWED_ORIGINS)
    print("CHANNELS_ALLOW_MISSING_ORIGIN:", settings.CHANNELS_ALLOW_MISSING_ORIGIN)
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
