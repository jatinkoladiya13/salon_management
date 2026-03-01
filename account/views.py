from rest_framework.permissions import IsAuthenticated
from django_tenants.utils import schema_context
from django.utils.http import urlsafe_base64_decode
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from utils.pagination import CustomPageNumberPagination
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ViewSet
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework import status
from account.models import User
from account.email import send_reset_password_email
from account.custom_token import CustomPasswordResetTokenGenerator
from django.db.models import Q
from account.serializers import *
from utils.permissions import IsPublicSchemaSuperUser, CustomPermission, IsTenantSuperAdmin
import utils.response_handler as rh
from core.constants import (
    SUPERADMIN_GROUP_NAME,
    READ_OWN_ACCOUNT_ONLY,
    UPDATE_OWN_ACCOUNT_ONLY,
)

# Create your views here
class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data= request.data,
            context={"schema_name": request.tenant.schema_name},
        )

        serializer.is_valid(raise_exception=True)
        
        response = rh.ResponseMsg(
            serializer.validated_data, False, "Login Successfully!!!"
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    
class RefreshTokenView(TokenRefreshView):
    serializer_class = TokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        serializer_data = super().post(request, *args, **kwargs)
        response = rh.ResponseMsg(
            serializer_data.data,
            False,
            "Access Token Get Successfully!!!",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)

class RegisterCustomer(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = NewAccountCreateSerializer(data = request.data)

        serializer.is_valid(raise_exception=True)
        serializer.save()

        response = rh.ResponseMsg(
            serializer.data, False, "Confirmation Email Send Successfully! Please Check Your Email.",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)


class UserView(ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    pagination_class = CustomPageNumberPagination
    search_fields = ["username", "email"]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return UserCreateSerializer
        return super(UserView, self).get_serializer_class()
    
    def get_permissions(self):

        if self.action == "create":
            return [AllowAny()]
        
        permission_classes = [IsAuthenticated]
        
        schema_name = self.request.GET.get("schema_name")
        if schema_name:
            permission_classes.append(IsPublicSchemaSuperUser)

        if self.action in ["list", "retrieve"]:
            permission_classes.append(CustomPermission(READ_OWN_ACCOUNT_ONLY))

        elif self.action in ["update", "partial_update"]:
            permission_classes.append(CustomPermission(UPDATE_OWN_ACCOUNT_ONLY))

        elif self.action in ["destroy", "delete_user_by_username"]:
            permission_classes.append(IsTenantSuperAdmin)

        elif self.action == "manage_profile_picture" and schema_name:
            permission_classes.append(IsPublicSchemaSuperUser)

        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.request.user.is_authenticated:
            return queryset.none()
        
        schema_name = self.request.GET.get("schema_name")
        if schema_name and not (
            self.request.user.is_superuser
            or self.request.user.get_role == SUPERADMIN_GROUP_NAME
        ):
            return queryset.distinct()
        
        print(
            "group:-",
            self.request.user.get_role,
            self.request.user.is_superuser,
        )

        if self.action in ["list", "retrieve"]:
            if is_permission(
                self.request.user.get_role,
                READ_OWN_ACCOUNT_ONLY
            ):
                queryset = queryset.filter(id=self.request.user.id)

            if self.action == "list":
                queryset = queryset.exclude(
                    email="support@experiense.ai",
                    groups__name=SUPERADMIN_GROUP_NAME,
                )

        elif self.action in ["update", "partial_update"]:
            if is_permission(
                self.request.user.get_role, UPDATE_OWN_ACCOUNT_ONLY
            ):
                queryset = queryset.filter(
                    id=self.request.user.id
                )

        elif self.action == "destroy":
            return queryset

        return queryset.distinct()
    
    def list(self, request, *args, **kwargs):
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                serializer_data = super().list(request, *args, **kwargs)
        else:
            serializer_data = super().list(request, *args, **kwargs)
        response = rh.ResponseMsg(
            serializer_data.data, False, "all users get Successfully!!!"
        )
        return Response(status=status.HTTP_200_OK, data=response.response)

    def create(self, request, *args, **kwargs):
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                serializer_data = super().create(request, *args, **kwargs)
        else:
            serializer_data = super().create(request, *args, **kwargs)

        response = rh.ResponseMsg(
            serializer_data.data, False, "New User Create Successfully!!"
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    
    def update(self, request, *args, **kwargs):
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                serializer_data = super().update(request, *args, **kwargs)
        else:
            serializer_data = super().update(request, *args, **kwargs)

        response = rh.ResponseMsg(
            serializer_data.data, False, "User updated Successfully!!"
        )
        return Response(status=status.HTTP_200_OK, data=response.response)
    
    def destroy(self, request, *args, **kwargs):
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                super().destroy(request, *args, **kwargs)
        else:
            super().destroy(request, *args, **kwargs)
        response = rh.ResponseMsg({}, False, "user deleted Successfully!!!")
        return Response(status=status.HTTP_200_OK, data=response.response)

    @action(
        methods=["POST"],
        detail=False,
        serializer_class = StaffCreateSerializer,
        permission_classes = [IsTenantSuperAdmin],
        url_path="staff",
    )
    def create_staff(self, request):
        serializer = StaffCreateSerializer(data=request.data)
        
        schema_name = request.GET.get("schema_name")
        if schema_name:
            with schema_context(schema_name):
                serializer.is_valid(raise_exception=True)
                serializer.save()
        else:
            serializer.is_valid(raise_exception=True)
            serializer.save()
        
        response = rh.ResponseMsg(
            serializer.data, False, "New Staff Create by Admin Successfully!!"
        )
        return Response(status=status.HTTP_200_OK, data=response.response)

class ForgotPasswordViewSet(ViewSet):

    @action(
        methods=["POST"],
        detail=False,
        permission_classes = [AllowAny],
        url_path="send-reset-link"
    )
    def send_password_resent_link(self, request):
        """
        Send reset password link to email
        """
        msg = "If the email is valid, a password reset link will be sent to the email."

        email = request.data.get("email", None)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise BadRequestException("User not Found with this email!!!")

        if user:
            send_reset_password_email(user, request.tenant.schema_name)

        response = rh.ResponseMsg({}, False, msg)
        return Response(
            status=status.HTTP_200_OK,
            data=response.response,
        )
    
    @action(
        methods=["POST"],
        detail=False,
        permission_classes=[AllowAny],
        url_path="reset-password",
    )
    def reset_password(self, request):
        """
        Reset Password
        """

        serializer = ResetForgotPasswordSerializers(data=request.data)
        if serializer.is_valid():
            uid =  urlsafe_base64_decode(request.data.get("uid")).decode()

            user = User.objects.filter(id=uid).first()
            if user is None:
                raise BadRequestException("Invalid Link!!!")
            
            custom_token_generator = CustomPasswordResetTokenGenerator()

            is_valid = custom_token_generator.check_token(
                user, request.data.get("token")
            )

            if is_valid:
                user.set_password(request.data.get("new_password"))
                user.save()
            else:
                raise BadRequestException("Invalid Link!!!")
            
            response = rh.ResponseMsg(
                {}, False, "Password Reset Successfully!!!"
            )
            return Response(
                status=status.HTTP_200_OK,
                data=response.response,
            )
        
        else:
            response = rh.ResponseMsg({}, True, serializer.errors)
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=response.response,
            )
