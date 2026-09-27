from django.urls import path, include
from rest_framework.routers import DefaultRouter
from salonDetails.views import *

router = DefaultRouter()


router.register("details", SalonDetailView, basename="salonDetails")

urlpatterns = [

    path("", include(router.urls))

]
