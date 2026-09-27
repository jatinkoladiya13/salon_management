from django.urls import path, include
from core.views import Groupview, PermissionStatusView
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("groups", Groupview),
router.register("permission_status",PermissionStatusView)

urlpatterns = [
    path("", include(router.urls))   
]
