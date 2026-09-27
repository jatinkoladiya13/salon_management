from unittest.mock import patch

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from PIL import Image

from django_tenants.utils import schema_context

from rest_framework import status
from rest_framework.exceptions import ValidationError

from account.custom_token import CustomPasswordResetTokenGenerator
from account.models import TwoFactorAuth
from account.serializers import NewAccountCreateSerializer, UserCreateSerializer
from core.constants import (
    DELETE_USERS_ACCOUNT, READ_OWN_ACCOUNT_ONLY, UPDATE_OWN_ACCOUNT_ONLY
)
from core.models import CustomGroup
from utils.testing import TenantAPITestCase

import pyotp

User = get_user_model()


class LoginApiTests(TenantAPITestCase):
    def test_login_returns_token_and_user_data(self):
        response = self.client.post(
            reverse("login"),
            {"email": self.admin.email, "password": self.PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["user_data"]["email"], self.admin.email)
        self.assertEqual(data["user_data"]["role"], self.admin_group.name)

    def test_login_with_wrong_password_is_rejected(self):
        response = self.client.post(
            reverse("login"),
            {"email": self.admin.email, "password": "NotMyPassword@1"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_is_refused_for_a_deactivated_user(self):
        with schema_context(self.tenant.schema_name):
            self.customer.is_active = False
            self.customer.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("login"),
            {"email": self.customer.email, "password": self.PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_returns_a_new_access_token(self):
        login = self.client.post(
            reverse("login"),
            {"email": self.admin.email, "password": self.PASSWORD},
            format="json",
        )
        refresh = login.data["data"]["refresh"]

        response = self.client.post(
            reverse("refresh-token"), {"refresh": refresh}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data["data"])


class ForgotPasswordApiTests(TenantAPITestCase):
    def url(self, action):
        return reverse(f"forgot-password-{action}")

    @patch("account.views.send_reset_password_email")
    def test_reset_link_is_sent_for_a_known_address(self, mock_send):
        response = self.client.post(
            self.url("send-password-resent-link"),
            {"email": self.customer.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_send.assert_called_once()

    @patch("account.views.send_reset_password_email")
    def test_unknown_address_gets_the_same_answer_and_sends_nothing(self, mock_send):
        """
        The endpoint must not reveal which addresses are registered - a
        different status or message for an unknown email turns it into an
        account-enumeration oracle.
        """
        known = self.client.post(
            self.url("send-password-resent-link"),
            {"email": self.customer.email},
            format="json",
        )
        unknown = self.client.post(
            self.url("send-password-resent-link"),
            {"email": "nobody-here@tenant.test"},
            format="json",
        )

        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.data["message"], unknown.data["message"])
        self.assertEqual(mock_send.call_count, 1)

    def test_missing_email_is_a_bad_request(self):
        response = self.client.post(
            self.url("send-password-resent-link"), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_is_reset_with_a_valid_token(self):
        with schema_context(self.tenant.schema_name):
            token = CustomPasswordResetTokenGenerator().make_token(self.customer)
            uid = urlsafe_base64_encode(force_bytes(self.customer.pk))

        response = self.client.post(
            self.url("reset-password"),
            {
                "uid": uid,
                "token": token,
                "new_password": "BrandNew@123",
                "confirm_password": "BrandNew@123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        with schema_context(self.tenant.schema_name):
            self.customer.refresh_from_db()
            self.assertTrue(self.customer.check_password("BrandNew@123"))

    def test_malformed_uid_is_rejected_without_a_server_error(self):
        response = self.client.post(
            self.url("reset-password"),
            {
                "uid": "!!!not-base64!!!",
                "token": "whatever",
                "new_password": "BrandNew@123",
                "confirm_password": "BrandNew@123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mismatched_passwords_are_rejected(self):
        response = self.client.post(
            self.url("reset-password"),
            {
                "uid": urlsafe_base64_encode(force_bytes(self.customer.pk)),
                "token": "irrelevant",
                "new_password": "BrandNew@123",
                "confirm_password": "Different@123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PasswordResetTokenTests(TenantAPITestCase):
    def test_token_round_trips_for_an_address_containing_a_hyphen(self):
        """
        The signed payload is "<email>-<expiry>", so an address with a hyphen in
        it used to break the unpack and lock that user out of password reset.
        """
        with schema_context(self.tenant.schema_name):
            user = User.objects.create_user(
                email="mary-jane@tenant.test",
                password=self.PASSWORD,
                groups=[self.user_group],
            )

            generator = CustomPasswordResetTokenGenerator()
            token = generator.make_token(user)

            self.assertTrue(generator.check_token(user, token))

    def test_token_is_rejected_for_a_different_user(self):
        with schema_context(self.tenant.schema_name):
            generator = CustomPasswordResetTokenGenerator()
            token = generator.make_token(self.customer)

            self.assertFalse(generator.check_token(self.staff, token))

    def test_garbage_token_is_rejected(self):
        with schema_context(self.tenant.schema_name):
            generator = CustomPasswordResetTokenGenerator()

            self.assertFalse(generator.check_token(self.customer, "nonsense"))
            self.assertFalse(generator.check_token(self.customer, ""))
            self.assertFalse(generator.check_token(self.customer, None))


class TwoFactorApiTests(TenantAPITestCase):
    def test_setup_returns_a_secret_and_qr_code(self):
        self.authenticate(self.customer)

        response = self.client.post(reverse("2fa-setup"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("secret", response.data["data"])
        self.assertIn("qr_code", response.data["data"])

    def test_verify_before_setup_is_a_bad_request_not_a_crash(self):
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("2fa-verify"), {"otp": "123456"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_enables_2fa_for_a_correct_code(self):
        self.authenticate(self.customer)
        setup = self.client.post(reverse("2fa-setup"))
        secret = setup.data["data"]["secret"]

        response = self.client.post(
            reverse("2fa-verify"),
            {"otp": pyotp.TOTP(secret).now()},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.assertTrue(
                TwoFactorAuth.objects.get(user=self.customer).is_enabled
            )

    def test_verify_rejects_a_wrong_code(self):
        self.authenticate(self.customer)
        self.client.post(reverse("2fa-setup"))

        response = self.client.post(
            reverse("2fa-verify"), {"otp": "000000"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_setup_twice_is_refused_once_enabled(self):
        self.authenticate(self.customer)
        secret = self.client.post(reverse("2fa-setup")).data["data"]["secret"]
        self.client.post(
            reverse("2fa-verify"), {"otp": pyotp.TOTP(secret).now()}, format="json"
        )

        response = self.client.post(reverse("2fa-setup"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_access_is_refused(self):
        response = self.client.post(reverse("2fa-setup"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserManagementApiTests(TenantAPITestCase):
    def test_list_requires_the_read_permission(self):
        self.authenticate(self.customer)

        self.grant(self.user_group, READ_OWN_ACCOUNT_ONLY, status=False)
        denied = self.client.get(reverse("usermanage-list"))
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.grant(self.user_group, READ_OWN_ACCOUNT_ONLY, status=True)
        allowed = self.client.get(reverse("usermanage-list"))
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

    def test_update_requires_the_update_permission(self):
        self.authenticate(self.customer)
        self.grant(self.user_group, UPDATE_OWN_ACCOUNT_ONLY, status=False)

        response = self.client.patch(
            reverse("usermanage-detail", args=[self.customer.id]),
            {"first_name": "Renamed"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_profile_image_can_be_updated_without_touching_other_fields(self):
        self.authenticate(self.customer)
        self.grant(self.user_group, UPDATE_OWN_ACCOUNT_ONLY, status=True)

        buffer = BytesIO()
        Image.new("RGB", (10, 10), color="blue").save(buffer, format="PNG")
        buffer.seek(0)
        image = SimpleUploadedFile(
            "profile.png",
            buffer.read(),
            content_type="image/png",
        )

        response = self.client.patch(
            reverse("usermanage-manage-profile-picture", args=[self.customer.id]),
            {"profile_image": image},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.customer.refresh_from_db()
            self.assertIsNotNone(self.customer.profile_image)

    def test_only_a_tenant_admin_can_delete_a_user(self):
        with schema_context(self.tenant.schema_name):
            victim = User.objects.create_user(
                email="victim@tenant.test",
                password=self.PASSWORD,
                groups=[self.user_group],
            )

        self.authenticate(self.customer)
        refused = self.client.delete(
            reverse("usermanage-detail", args=[victim.id])
        )
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.admin)
        self.grant(self.admin_group, DELETE_USERS_ACCOUNT, status=True)
        allowed = self.client.delete(
            reverse("usermanage-detail", args=[victim.id])
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

        with schema_context(self.tenant.schema_name):
            self.assertFalse(User.objects.filter(id=victim.id).exists())

    def test_staff_creation_is_restricted_to_a_tenant_admin(self):
        payload = {
            "email": "new-staff@tenant.test",
            "password": "Str0ng@Pass1",
            "first_name": "New",
            "last_name": "Staff",
            "mobile": "+919876543210",
        }

        self.authenticate(self.customer)
        refused = self.client.post(
            reverse("usermanage-create-staff"), payload, format="json"
        )
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.admin)
        allowed = self.client.post(
            reverse("usermanage-create-staff"), payload, format="json"
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

        with schema_context(self.tenant.schema_name):
            created = User.objects.get(email="new-staff@tenant.test")
            self.assertEqual(created.get_role, self.staff_group.name)

    def test_staff_is_placed_in_the_staff_group_by_name_not_by_id(self):
        """The group used to be looked up by hardcoded primary key, which
        assigns the wrong role as soon as the rows are recreated in a different
        order."""
        with schema_context(self.tenant.schema_name):
            group_name = self.staff_group.name
            original_id = self.staff_group.pk
            CustomGroup.objects.filter(name=group_name).delete()
            regenerated = CustomGroup.objects.create(name=group_name, level=2)
            self.assertNotEqual(regenerated.id, original_id)

        self.authenticate(self.admin)
        response = self.client.post(
            reverse("usermanage-create-staff"),
            {
                "email": "renumbered-staff@tenant.test",
                "password": "Str0ng@Pass1",
                "first_name": "Re",
                "last_name": "Numbered",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            created = User.objects.get(email="renumbered-staff@tenant.test")
            self.assertEqual(created.groups.first().pk, regenerated.pk)

    def test_assigning_two_groups_at_once_is_a_validation_error(self):
        with schema_context(self.tenant.schema_name):
            serializer = UserCreateSerializer(
                instance=self.customer,
                data={"groups": [self.staff_group.id, self.user_group.id]},
                partial=True,
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)

            with self.assertRaises(ValidationError):
                serializer.save()


class RegistrationSerializerTests(TenantAPITestCase):
    def base_payload(self, **overrides):
        payload = {
            "user_email": "owner@bellasalon.co",
            "user_first_name": "Mary Jane",
            "user_last_name": "Watson",
            "organization_email": "hello@bellasalon.co",
            "password": "Str0ng@Pass1",
            "confirm_password": "Str0ng@Pass1",
            "organisation_slug": "bellasalon",
            "mobile_number": "+919876543210",
        }
        payload.update(overrides)
        return payload

    def test_a_first_name_containing_a_space_is_accepted(self):
        """
        The check used to be ``value.replace("", "")``, a no-op, so every
        two-part first name was rejected at signup.
        """
        serializer = NewAccountCreateSerializer(data=self.base_payload())

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_a_numeric_name_is_still_rejected(self):
        serializer = NewAccountCreateSerializer(
            data=self.base_payload(user_first_name="Mary123")
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("user_first_name", serializer.errors)

    def test_reserved_workspace_names_are_refused(self):
        for reserved in ("public", "admin"):
            serializer = NewAccountCreateSerializer(
                data=self.base_payload(organisation_slug=reserved)
            )

            self.assertFalse(serializer.is_valid(), reserved)
            self.assertIn("organisation_slug", serializer.errors)

    def test_workspace_name_is_normalised_to_lower_case(self):
        serializer = NewAccountCreateSerializer(
            data=self.base_payload(organisation_slug="BellaSalon")
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["organisation_slug"], "bellasalon"
        )

    def test_a_public_mailbox_is_rejected_for_the_owner_address(self):
        serializer = NewAccountCreateSerializer(
            data=self.base_payload(user_email="someone@gmail.com")
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("user_email", serializer.errors)

    def test_mismatched_passwords_are_rejected(self):
        serializer = NewAccountCreateSerializer(
            data=self.base_payload(confirm_password="Different@1")
        )

        with self.assertRaises(Exception):
            serializer.is_valid(raise_exception=True)


class ElasticsearchViewTests(TenantAPITestCase):
    def test_reindex_is_refused_for_a_plain_customer(self):
        self.authenticate(self.customer)

        response = self.client.post(reverse("search-users"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("account.views.es")
    def test_search_maps_uuid_document_ids_back_to_users(self, mock_es):
        """
        User ids are UUIDs. The view used to call int() on the Elasticsearch
        document id, which raised ValueError for every real result.
        """
        mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": str(self.customer.id)},
                    {"_id": "not-a-uuid"},
                ]
            }
        }

        self.authenticate(self.admin)
        response = self.client.get(reverse("search-users"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned = [row["email"] for row in response.data["data"]]
        self.assertEqual(returned, [self.customer.email])
