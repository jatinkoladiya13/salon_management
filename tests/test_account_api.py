from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import schema_context
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django_tenants.test.client import TenantClient
from django.core.cache import cache
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch, MagicMock
from contextlib import contextmanager

from core.constants import TENANTADMIN_GROUP_NAME, TENANTSTAFF_GROUP_NAME, TENANTUSER_GROUP_NAME 
from core.models import CustomGroup
from subscription.models.models import SubscriptionPlan
from account.custom_token import CustomPasswordResetTokenGenerator

from faker import Faker


User = get_user_model()

fake = Faker()

class AccountApiTests(TenantTestCase):
    HOST = "test.localhost"

    ADMIN_EMAIL = "admin@test.com"
    ADMIN_PASSWORD = "Test@12345"

    AGENT_EMAIL = fake.email()
    AGENT_PASSWORD = fake.password()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.domain.domain = cls.HOST
        cls.domain.save()
        
        cls.tenant.create_schema(check_if_exists=True, verbosity=0)
        call_command(
            "migrate_schemas",
            schema_name=cls.tenant.schema_name,
            interactive=False,
            verbosity=0
        )

    def setUp(self):
        cache.clear()

        self.client = APIClient()
        self.client.defaults["HTTP_HOST"] = self.HOST


        with schema_context(self.tenant.schema_name):

            # Ensure Groups exist with correct IDs for the hardcoded serializers
            # We delete existing to reset IDs if possible and recreate them
            CustomGroup.objects.all().delete()

            # ID 1: SuperAdmin/TenantAdmin (Used in NewAccountCreateSerializer)
            self.tenant_admin_group = CustomGroup.objects.create(id=1, name=TENANTADMIN_GROUP_NAME, level=1)
            
            # ID 2: Staff (Used in StaffCreateSerializer)
            self.staff_group = CustomGroup.objects.create(id=2, name=TENANTSTAFF_GROUP_NAME, level=2)
            
            # ID 3: User (Used in UserCreateSerializer)
            self.user_group = CustomGroup.objects.create(id=3, name=TENANTUSER_GROUP_NAME, level=3)

            self.admin = User.objects.create_user(
                email=self.ADMIN_EMAIL,
                password=self.ADMIN_PASSWORD,
                first_name="Admin",
                last_name="User",
                is_active=True,
                groups=[self.tenant_admin_group],
            )

        # Create SubscriptionPlan in public schema (assuming shared) for RegisterCustomer test
        with schema_context("public"):
             if not SubscriptionPlan.objects.filter(slug="trial_subscription").exists():
                SubscriptionPlan.objects.create(
                    slug="trial_subscription",
                    interval="trial",
                    credits_minutes=100,
                    name="Trial"
                )

        self.create_admin_and_login()
           
    
    def create_admin_and_login(self):
        login_url = reverse("login")
        payload = {
            "email": self.admin.email, 
            "password": self.ADMIN_PASSWORD
        }

        token_res = self.client.post(login_url, payload, format="json")
        self.assertEqual(token_res.status_code, status.HTTP_200_OK)

        access_token = token_res.data["data"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
       
    def test_login_api(self):
        url = reverse("login")
        # Test success
        payload = {"email": self.ADMIN_EMAIL, "password": self.ADMIN_PASSWORD}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["data"])

        # Test failure
        payload = {"email": self.ADMIN_EMAIL, "password": "WrongPassword"}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token(self):

        url = reverse("refresh-token")

        refresh = RefreshToken.for_user(self.admin)
        payload = {"refresh": str(refresh)}
        
        response  = self.client.post(url, payload,  format="json")
        # print("response data:", response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["data"])

    @patch("account.serializers.create_tenant_and_domain")
    @patch("account.serializers.schema_context")
    @patch("account.serializers.CallCredit")
    @patch("account.serializers.User") 
    def test_register_customer(self, mock_user_model, mock_call_credit, mock_schema_context, mock_create_tenant):
        """
        Test customer registration.
        Mocks tenant creation and schema switching to avoid DDL in transaction.
        """
        # Setup mocks
        mock_tenant = type("Tenant", (), {"schema_name": "newsalon", "subscription_end_date": "2030-01-01"})
        mock_create_tenant.return_value = mock_tenant
        
        # Mock schema_context to be a no-op context manager
        @contextmanager
        def mock_ctx(name):
            yield
        mock_schema_context.side_effect = mock_ctx

        # Mock User creation inside the serializer
        mock_user_instance = MagicMock()
        mock_user_instance.id = 1
        mock_user_instance.email = "newclient@business.com"
        mock_user_model.objects.create_user.return_value = mock_user_instance

        url = "/api/account/register/"
        payload = {
            "user_email": "newclient@business.com",
            "user_first_name": "New",
            "user_last_name": "Client",
            "organisation_name": "New Salon",
            "organisation_email": "info@newsalon.com",
            "password": "Password@123",
            "confirm_password": "Password@123",
            "organisation_slug": "newsalon",
            "mobile_number": "+1234567890"
        }
        
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Confirmation Email Send Successfully! Please Check Your Email.")

    @patch("account.views.CustomPermission")
    def test_user_management_crud(self, mock_custom_permission):
        """
        Test List, Create, Retrieve, Update, Delete for Users.
        """
        # Mock permission to allow access
        mock_instance = MagicMock()
        mock_instance.has_permission.return_value = True
        mock_custom_permission.return_value = mock_instance

        # List
        url_list = reverse("usermanage-list")
        response = self.client.get(url_list)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Create (User)
        # UserCreateSerializer automatically assigns group ID 3
        url_create = reverse("usermanage-list")
        payload_create = {
            "email": "staffmember@test.com",
            "password": "Password@123",
            "first_name": "Staff",
            "last_name": "Member",
            "mobile": "+9876543210",
            "date_of_birth": "1990-01-01"
        }
        
        response = self.client.post(url_create, payload_create, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_user_id = response.data["data"]["id"]
        
        # Retrieve
        url_detail = reverse("usermanage-detail", args=[new_user_id])
        response = self.client.get(url_detail)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "staffmember@test.com")
        
        # Update
        payload_update = {
            "first_name": "UpdatedStaff"
        }
        response = self.client.patch(url_detail, payload_update, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["first_name"], "UpdatedStaff")
        
        # Delete
        response = self.client.delete(url_detail)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
    def test_create_staff(self):
        """
        Test creating a staff member (Group ID 2).
        """
        url = reverse("usermanage-create-staff")
        payload = {
            "email": "realstaff@test.com",
            "password": "Password@123",
            "first_name": "Real",
            "last_name": "Staff",
            "mobile": "+1122334455",
            "date_of_birth": "1990-01-01"
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["email"], "realstaff@test.com")

    def test_forgot_password_flow(self):
        """
        Test sending reset link and resetting password.
        """
        # 1. Send Link
        url_send = reverse("forgot-password-send-password-resent-link")
        payload = {"email": self.ADMIN_EMAIL}
        
        with patch("account.views.send_reset_password_email") as mock_send_email:
            response = self.client.post(url_send, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_send_email.assert_called_once()

        self.admin.refresh_from_db()    
        # 2. Reset Password
        # Generate valid token and uid for the admin user
        token = CustomPasswordResetTokenGenerator().make_token(self.admin)
        uid = urlsafe_base64_encode(force_bytes(self.admin.pk))
        
        url_reset = reverse("forgot-password-reset-password")
        payload_reset = {
            "uid": uid,
            "token": token,
            "new_password": "NewPassword@123",
            "confirm_password": "NewPassword@123"
        }
        
        response = self.client.post(url_reset, payload_reset, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify login with new password
        login_url = reverse("login")
        login_payload = {"email": self.ADMIN_EMAIL, "password": "NewPassword@123"}
        response = self.client.post(login_url, login_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    @classmethod
    def tearDownClass(cls):
        pass

    