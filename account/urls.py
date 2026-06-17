from django.urls import path, include
from account.views import *
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("usermanage", UserView, basename="usermanage")
router.register("forgot-password", ForgotPasswordViewSet, basename="forgot-password")

urlpatterns = [
    path("", include(router.urls)),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh_token/", RefreshTokenView.as_view(), name="refresh-token"),
    
    path("register/", RegisterCustomer.as_view()),

    path("search/", GetInElasticsearchView.as_view(), name="search-users"),

    path("2fa-setup/", Setup2FAView.as_view(), name="2fa-setup"),
    path("2fa-verify/", Verify2FAView.as_view(), name="2fa-verify"),

]
