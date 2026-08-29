from django.utils.http import urlsafe_base64_decode
from django_tenants.utils import schema_context
from django.db.models import Q
import logging

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework.viewsets import ModelViewSet, ViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework import filters
from rest_framework import status

from account.custom_token import CustomPasswordResetTokenGenerator
from account.utils import generate_secret, generate_qr_code
from account.email import send_reset_password_email
from account.models import User, TwoFactorAuth
from account.serializers import *

from utils.elasticsearch_client import es, data_to_elasticsearch
from utils.pagination import CustomPageNumberPagination
from utils.custom_exception import BadRequestException
from utils.permissions import (
    IsPublicSchemaSuperUser,
    CustomPermission,
    IsTenantSuperAdmin,
    IsAdmin,
)

import utils.response_handler as rh
from core.constants import (
    SUPERADMIN_GROUP_NAME,
    READ_USERS_ACCOUNT,
    CREATE_USERS_ACCOUNT,
    UPDATE_USERS_ACCOUNT,
    DELETE_USERS_ACCOUNT,
    CREATE_OWN_ACCOUNT_ONLY,
    READ_OWN_ACCOUNT_ONLY,
    UPDATE_OWN_ACCOUNT_ONLY,
    DELETE_OWN_ACCOUNT_ONLY,
)
import pyotp
import uuid

logger = logging.getLogger(__name__)

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
    permission_classes = [IsPublicSchemaSuperUser]

    def post(self, request):
        serializer = NewAccountCreateSerializer(data = request.data)

        serializer.is_valid(raise_exception=True)
        serializer.save()

        response = rh.ResponseMsg(
            serializer.data, False, "Confirmation Email Send Successfully! Please Check Your Email.",
        )
        return Response(status=status.HTTP_200_OK, data=response.response)

class GetInElasticsearchView(APIView):
    # Re-indexing walks every user in the schema, so it is an admin operation,
    # not something any signed-in customer should be able to trigger.
    permission_classes = [IsAdmin]

    def post(self, request):

        # Production you can run this code in a separate management command and index your data in elasticsearch and then you can use search API to search data from elasticsearch
        
        index_name = "users"
        
        docs = []
        
        for user in User.objects.all():
            doc = {
                "username": user.username,
                "email": user.email,
                "role": user.get_role,
                "is_active": user.is_active,
                "is_verify": user.is_verify,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "mobile": user.mobile,
                "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
            }
            docs.append({
                "_index": index_name,
                "_id": user.id,
                "_source": doc
            })

        success, errors = data_to_elasticsearch(docs, index_name)

        # print(f"Bulk indexing response: {bulk_response}")

        # es.indices.delete(index="users", ignore=[400, 404])
        # mapping = {
        #     "mappings": {
        #         "properties": {
        #             "username": {"type": "text"},
        #             "email": {"type": "text"},
        #             "role": {"type": "keyword"},
        #             "is_active": {"type": "boolean"},
        #             "is_verify": {"type": "boolean"},
        #             "last_login" : {"type": "date"},
        #             "mobile": {"type": "text"},
        #             "date_of_birth":{"type": "date"}
        #         }
        #     }
        # }

        # es.indices.create(index="users", body=mapping)

        # for user in User.objects.all():
        #     print("indexing user:-", user.username)
        #     doc = {
        #         "username": user.username,
        #         "email": user.email,
        #         "role": user.get_role,
        #         "is_active": user.is_active,
        #         "is_verify": user.is_verify,
        #         "last_login": user.last_login.isoformat() if user.last_login else None,
        #         "mobile": user.mobile,
        #         "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
        #     }
        #     es.index(index="users", id=user.id, body=doc)

        response = rh.ResponseMsg(
                {
                    "success_count": success,
                    "errors": errors
                }, False, "Data Indexed in Elasticsearch Successfully!!!"
            )
        return Response(status=status.HTTP_200_OK, data=response.response)    

    def get(self, request):
        search_query = request.GET.get("search", None)
        role = request.GET.get("role", None)
        is_active = request.GET.get("is_active", None)
        start_date = request.GET.get("start_date", None)
        end_date = request.GET.get("end_date", None)
    
        query = {
            "bool": {
                "must": [],
                "filter": [],
                "must_not": [],
                "should": []
            }
        }
       

        if search_query:
            query["bool"]["must"].append({
                "multi_match": {
                    "query": search_query,
                    "fields": ["username", "email"],
                    "type": "phrase_prefix"
                }
            })

        if role:
            query["bool"]["filter"].append({"term": {"role": role}})

        if is_active is not None:
            is_active_value = is_active.lower() == "true"
            query["bool"]["filter"].append({"term": {"is_active": is_active_value}})  
      
        if start_date and end_date:
            query["bool"]["filter"].append({
                "range": {
                    "last_login": {
                        "gte": start_date,
                        "lte": end_date
                    }
                }
            })    
        
        # Never surface these in search results. Two separate clauses: as a
        # single dict the duplicate "match" key silently dropped the first one.
        query["bool"]["must_not"].append(
            {"match": {"email": "jatinkoladiya130@gmail.com"}}
        )
        query["bool"]["must_not"].append({"term": {"is_active": False}})

        # This is multiple value filter example if you want to filter with multiple status like active and inactive both then you can use this code
        # status = request.GET.get("status")
        # if status:
        #     status_list = status.split(",")

        #     query["bool"]["filter"].append({
        #         "terms": {
        #             "status.keyword": status_list
        #         }
        #     })

        results = es.search(
            index="users",
            query=query
        )

        hits = results["hits"]["hits"]

        # User ids are UUIDs; Elasticsearch returns them as strings. Anything
        # that is no longer a valid id (stale index entry) is skipped rather
        # than blowing up the whole search.
        user_ids = []
        for hit in hits:
            try:
                user_ids.append(uuid.UUID(str(hit["_id"])))
            except (ValueError, TypeError, KeyError):
                continue

        users = User.objects.filter(id__in=user_ids)
        serializer = UserSerializer(users, many=True)
        response = rh.ResponseMsg(
            serializer.data, False, "Users data get Successfully!!"
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

        # Extra @action endpoints declare their own permission_classes, which
        # the router has already applied to this instance. Overriding
        # get_permissions() without honouring them silently dropped those
        # checks - create_staff fell through to plain IsAuthenticated, letting
        # any signed-in customer promote themselves to Staff.
        extra_actions = {
            action.__name__ for action in self.get_extra_actions()
        }
        if self.action in extra_actions:
            return super().get_permissions()

        permission_classes = [IsAuthenticated]

        schema_name = self.request.GET.get("schema_name")
        if schema_name:
            permission_classes += [IsPublicSchemaSuperUser]


        if self.action in ["list", "retrieve"]:
            permission_classes += [
                CustomPermission(READ_USERS_ACCOUNT)
                | CustomPermission(READ_OWN_ACCOUNT_ONLY)
            ]

        elif self.action == "create":
            permission_classes += [
                CustomPermission(CREATE_USERS_ACCOUNT)
                | CustomPermission(CREATE_OWN_ACCOUNT_ONLY)
            ]

        elif self.action in ["update", "partial_update"]:
                permission_classes += [
                    CustomPermission(UPDATE_USERS_ACCOUNT)
                    | CustomPermission(UPDATE_OWN_ACCOUNT_ONLY)
                ]  

        elif self.action in ["destroy"]:
            permission_classes += [
                CustomPermission(DELETE_USERS_ACCOUNT)
                | CustomPermission(DELETE_OWN_ACCOUNT_ONLY)
            ]

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
        
        if self.action in ["list", "retrieve"]:
            if is_permission(
                self.request.user.get_role,
                READ_OWN_ACCOUNT_ONLY
            ):
                pass 
                # queryset = queryset.filter(id=self.request.user.id)

            if self.action == "list":
                queryset = queryset.exclude(
                    email="support@experiense.ai",
                    groups__name=SUPERADMIN_GROUP_NAME,
                )

        elif self.action in ["update", "partial_update"]:
            user_role = self.request.user.get_role
            can_update_users = is_permission(user_role, UPDATE_USERS_ACCOUNT)
            can_update_own_only = is_permission(user_role, UPDATE_OWN_ACCOUNT_ONLY)

            if can_update_own_only and not can_update_users:
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
            serializer_data =super().list(request, *args, **kwargs)

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
        
        with schema_context(request.tenant.schema_name):
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
        logger.info("=" * 50)
        logger.info("Password reset request initiated")
        
        msg = "If the email is valid, a password reset link will be sent to the email."

        email = request.data.get("email", None)
        logger.info(f"Email provided: {email}")

        if not email:
            logger.warning("Password reset attempted without email")
            raise BadRequestException("Email is required.")

        # Deliberately identical response whether or not the account exists:
        # answering "User not Found with this email" turns this endpoint into a
        # way to enumerate which addresses are registered.
        logger.info(f"Searching for active user with email: {email}")
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user:
            logger.info(f"User found: {user.id} - {user.email}")
            logger.info(f"Sending password reset email to: {email}")
            try:
                send_reset_password_email(user, request.tenant.schema_name)
                logger.info(f"Password reset email sent successfully to: {email}")
            except Exception as e:
                logger.error(f"Failed to send password reset email to {email}: {str(e)}", exc_info=True)
        else:
            logger.info(f"No active user found with email: {email} (This is intentional for security)")

        logger.info("Returning generic success response")
        response = rh.ResponseMsg({}, False, msg)
        logger.info("=" * 50)
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
            # A hand-edited link gives a malformed uid; treat it as an invalid
            # link instead of letting the decode/lookup raise a 500.
            try:
                uid = urlsafe_base64_decode(
                    serializer.validated_data["uid"]
                ).decode()
                user = User.objects.filter(id=uuid.UUID(uid)).first()
            except (ValueError, TypeError, UnicodeDecodeError):
                raise BadRequestException("Invalid Link!!!")

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


class Setup2FAView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
 
        obj, created  = TwoFactorAuth.objects.get_or_create(user=user)

        if obj.is_enabled:
            response = rh.ResponseMsg({}, True, "2FA already enabled")
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=response.response,
            )
        
        secret = generate_secret()
        obj.secret = secret
        obj.save()

        qr = generate_qr_code(user.username, secret)

        data = {
            "qr_code": qr,
            "secret": secret 
        }

        response = rh.ResponseMsg(
            data, False, "Get qr code and secret successfully!!!"
        )
        return Response(status=status.HTTP_200_OK, data=response.response,)


class Verify2FAView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        otp = request.data.get("otp")

        if not otp:
            response = rh.ResponseMsg({}, True, "OTP is required")
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data=response.response
            )

        obj = TwoFactorAuth.objects.filter(user=request.user).first()
        if obj is None or not obj.secret:
            response = rh.ResponseMsg(
                {}, True, "2FA is not set up for this account. Call 2fa-setup first."
            )
            return Response(
                status=status.HTTP_400_BAD_REQUEST, data=response.response
            )

        totp = pyotp.TOTP(obj.secret)

        if totp.verify(str(otp)):
            obj.is_enabled = True
            obj.save()
            response = rh.ResponseMsg(
                {}, False, "2FA enabled successfully"
            )
            return Response(status=status.HTTP_200_OK, data=response.response)
        else:
            response = rh.ResponseMsg({}, True, "Invalid OTP")
            return Response(
                status=status.HTTP_400_BAD_REQUEST,
                data=response.response,
            )
