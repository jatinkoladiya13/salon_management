from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceViewSet, StaffServiceViewSet, TimeSlotViewSet, AppointmentViewSet
from .consumers import NotificationConsumer

router = DefaultRouter()
router.register("services", ServiceViewSet, basename="services")
router.register("staff-services", StaffServiceViewSet, basename="staff-services")
router.register("timeslots", TimeSlotViewSet, basename="timeslots")
router.register("appointments", AppointmentViewSet, basename="appointments")

urlpatterns = [
    path("", include(router.urls))
]


