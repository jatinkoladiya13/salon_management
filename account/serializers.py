from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model

from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context
from tenant.views import create_tenant_and_domain
from django.db import transaction
from tenant.models import Tenant

# from subscription.models.models import SubscriptionPlan
from salonDetails.models import SalonDetails

from core.models.group import CustomGroup
from core.constants import (
    TENANTADMIN_GROUP_NAME,
    TENANTSTAFF_GROUP_NAME,
    TENANTUSER_GROUP_NAME,
)
from account.functions import validate_user_data
from decouple import config

from utils.custom_exception import BadRequestException
from utils.helpers import is_permission

User = get_user_model()

# Schema names that a customer must never be able to claim during signup.
RESERVED_SCHEMA_NAMES = {
    "public",
    "template",
    "information_schema",
    "pg_catalog",
    "pg_toast",
    "admin",
    "api",
    "www",
}


class LoginSerializer(TokenObtainPairSerializer):
    
    def __init__(self, *args, **kwargs):
        self.schema_name = kwargs["context"].pop("schema_name", None)
        super().__init__(*args, **kwargs)

    def get_token(self, user):
        token = super().get_token(user)
        token["schema_name"] = self.schema_name

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        tenant = Tenant.objects.filter(schema_name=self.schema_name).first()
        if tenant is None:
            raise BadRequestException("Unknown workspace.")

        data["user_data"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": self.user.get_role,
        }
            
        with schema_context("public"):
            data["company_logo"] = None
            if tenant.salonDetails:
                if tenant.salonDetails.company_logo:
                    data["company_logo"] = tenant.salonDetails.company_logo.url
        return data   
    

class NewAccountCreateSerializer(serializers.Serializer):
    schema_name = serializers.CharField(read_only=True)
    user_email = serializers.EmailField(required=True)
    user_first_name  = serializers.CharField(max_length=255, required=True)
    user_last_name = serializers.CharField(max_length=255, required=True)

    organization_email = serializers.CharField(
        max_length=150, required=True, allow_blank=False
    )
    organisation_email = serializers.EmailField(
        allow_blank=True, required=False
    )
    
    password = serializers.CharField(
        write_only=True, min_length=8, max_length=100, required=True
    )
    confirm_password = serializers.CharField(
        write_only=True, min_length=8, max_length=100, required=True
    )

    organisation_slug = serializers.CharField(max_length=20, required=True)
    organisation_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True
    )

    mobile_number = serializers.CharField(max_length=20, required=True)

    def validate_user_first_name(self, value):
        value = value.strip()
        # replace(" ", "") - the old replace("", "") was a no-op, so any name
        # with a space in it ("Mary Jane") was rejected at signup.
        if not value.replace(" ", "").isalpha():
            raise serializers.ValidationError(
                "First name should only contain alphabets"
            )
        return value
    
    def validate_user_last_name(self, value):
        value = value.strip()
        if not value.replace(" ", "").isalpha():
            raise serializers.ValidationError(
                "Last name should only contain alphabets"
            )
        return value
    
    def validate_organisation_slug(self, value):
        value = value.strip().lower()

        if not value:
            raise serializers.ValidationError("Workspace name is required.")

        if not all(
            char.isalpha()
            or (char == "_" and idx > 0 and value[idx - 1] != "_")
            for idx, char in enumerate(value)
        ):
            raise serializers.ValidationError(
                "Organisation slug should only contain alphabets and underscore, and two underscore should not appear together"
            )

        # The slug becomes a Postgres schema name, so the reserved ones have to
        # be refused here rather than failing during schema creation.
        if value in RESERVED_SCHEMA_NAMES:
            raise serializers.ValidationError("This workspace name is reserved.")

        if Tenant.objects.filter(schema_name=value).exists():
            raise serializers.ValidationError("Workspace name already exists.")
        return value
    
    def validate_organization_email(self, value):
        public_mail = [
            "gmail",
            "yahoo",
            "outlook",
            "hotmail",
            "live",
            "zoho",
            "protonmail",
            "aol",
            "icloud",
            "zohomail",
        ]
        if any(f"@{mail}" in value for mail in public_mail):
            raise serializers.ValidationError(
                "Please enter your Bussiness email address in organization email field."
            )
        return value
    
    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages)

        return value
    
    def validate(self, data):
        """
            Custom validation for password matching.
        """
        password = data.get("password")
        confirm_password = data.get("confirm_password")
        if password != confirm_password:
            raise BadRequestException("Passwords do not match.")

        return data
    
    def create(self, validated_data):
        with transaction.atomic():

            slug = validated_data.get("organisation_slug")

            salonDetails = SalonDetails.objects.create(
                # organisation_name is optional; without the fallback every new
                # salon was created with name=None.
                name=validated_data.get("organisation_name") or slug,
                organization_email=validated_data.get("organization_email"),
                phone_number=validated_data.get("mobile_number"),
                slug=slug,
                status="active",
            )

            tenant = create_tenant_and_domain(
                slug,
                slug + "." + config("HOST_URI"),
                salonDetails.id,
            )

            with schema_context(tenant.schema_name):
                group = CustomGroup.objects.get(name=TENANTADMIN_GROUP_NAME)
                User.objects.create_user(
                    email=validated_data.get("user_email"),
                    password=validated_data.get("password"),
                    groups=[group],
                    first_name=validated_data.get("user_first_name"),
                    last_name=validated_data.get("user_last_name"),
                    is_active=True,
                    is_verify=True
                )

            validated_data["schema_name"] = tenant.schema_name

        return validated_data
    
class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        exclude = (
            "password",
            "user_permissions",
        )

    def get_role(self, obj):
        group = obj.groups.first()
        return group.name if group else None

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(validators=[validate_password])

    class Meta:
        model = User
        fields = (
            "groups",
            "password",
            "is_active",
            "is_verify",
            # "username",
            "email",
            "first_name",
            "last_name",
            "date_of_birth",
            "mobile",
        )

    def to_representation(self, instance):
        return UserSerializer(instance).data
    
    def validate_password(self, value):
        if " " in value:
            raise serializers.ValidationError(
                "Password should not contain any space."
            )
        
        if not any(char.isdigit() for char in value):
            raise serializers.ValidationError(
                "Password should contain at least one digit."
            )
        
        if not any(char.isupper() for char in value):
            raise serializers.ValidationError(
                "Password should contain at least one uppercase."
            )
        if not any(char.islower() for char in value):
            raise serializers.ValidationError(
                "Password should contain at least one lowercase."
            )
        if not any(char in '!@#$%^&*()_+}{":?><,./;' for char in value):
            raise serializers.ValidationError(
                "Password should contain at least one special character."
            )
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            email = validated_data.get("email"),
            password = validated_data.get("password"),
            groups=[CustomGroup.objects.get(name=TENANTUSER_GROUP_NAME)],
            first_name=validated_data.get("first_name"),
            last_name=validated_data.get("last_name"),
            date_of_birth = validated_data.get("date_of_birth"),
            mobile = validated_data.get("mobile"),
            is_active=True
        )
        user.save()
        return user
    
    def update(self, instance, validated_data):
        groups = validated_data.pop("groups", [])
        password = validated_data.pop("password", None)

        if len(groups) > 1:
            # serializers.ValidationError, not Django's - the Django one is not
            # an APIException and used to surface as a server error.
            raise serializers.ValidationError(
                {"groups": "You can assign only one group at a time to User!"}
            )

        # new_email= validated_data.get("email")
        # if new_email and new_email != instance.email:
        user = super().update(instance, validated_data)

        if password:
            user.set_password(password)
            user.save()

        if groups:
           user.groups.clear()  
           user.groups.add(groups[0])
        return user

class StaffCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(validators=[validate_password])

    class Meta:
        model = User
        fields = (
            "groups",
            "password",
            "is_active",
            "is_verify",
            # "username",
            "email",
            "first_name",
            "last_name",
            "date_of_birth",
            "mobile",
        )

    def to_representation(self, instance):
        return UserSerializer(instance).data
    
    def validate_password(self, value):
        if " " in value:
            raise serializers.ValidationError(
                "Password should not contain any space."
            )
        
        if not any(char.isdigit() for char in value):
            raise serializers.ValidationError(
                "Password should contain at least one digit."
            )
        
        if not any(char.isupper() for char in value):
            raise serializers.ValidationError(
                "Password should contain at least one uppercase."
            )
        if not any(char.islower() for char in value):
            raise serializers.ValidationError(
                "Password should contain at least one lowercase."
            )
        if not any(char in '!@#$%^&*()_+}{":?><,./;' for char in value):
            raise serializers.ValidationError(
                "Password should contain at least one special character."
            )
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            email = validated_data.get("email"),
            password = validated_data.get("password"),
            groups=[CustomGroup.objects.get(name=TENANTSTAFF_GROUP_NAME)],
            first_name=validated_data.get("first_name"),
            last_name=validated_data.get("last_name"),
            date_of_birth = validated_data.get("date_of_birth"),
            mobile = validated_data.get("mobile"),
            is_active=True,
        )
        user.save()
        return user
    
class ResetForgotPasswordSerializers(serializers.Serializer):
    uid  = serializers.CharField(required=True)
    token = serializers.CharField(required =True)
    new_password = serializers.CharField(max_length=100, required=True)
    confirm_password = serializers.CharField(max_length=100, required=True)

    def validate(self, data):
        new_password = data.get("new_password")
        confirm_password = data.get("confirm_password")

        if new_password != confirm_password:
            raise serializers.ValidationError("Passwords do not match.")
        # password should not contain any space
        if " " in new_password:
            raise serializers.ValidationError(
                "Password should not contain any space."
            )
        # password should not contain at least one digit, one uppercase, one lowercase and one special character
        if not any(char.isdigit() for char in new_password):
            raise serializers.ValidationError(
                "Password should contain at least one digit."
            )
        if not any(char.isupper() for char in new_password):
            raise serializers.ValidationError(
                "Password should contain at least one uppercase."
            )
        if not any(char.islower() for char in new_password):
            raise serializers.ValidationError(
                "Password should contain at least one lowercase."
            )
        if not any(char in '!@#$%^&*()_+}{":?><,./;' for char in new_password):
            raise serializers.ValidationError(
                "Password should contain at least one special character."
            )
        return data
