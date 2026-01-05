from django.urls import path, include
from account.views import *
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("usermanage", UserView, basename="usermanage")
router.register("forgot-password", ForgotPasswordViewSet, basename="forgot-password")

urlpatterns = [
    path("", include(router.urls)),
    path("login/", LoginView.as_view()),
    path("refresh_token/", RefreshTokenView.as_view()),
    path("register/", RegisterCustomer.as_view()),


]
