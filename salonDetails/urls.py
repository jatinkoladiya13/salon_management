from django.urls import path, include
from rest_framework.routers import DefaultRouter
from salonDetails.views import *

router = DefaultRouter()


router.register("details", SalonDetailView, basename="salonDetails")
router.register("opening-hours", SalonOpeningHoursView, basename="opening-hours")

urlpatterns = [

    path("", include(router.urls))

]
