from unittest.mock import patch

from django.urls import reverse

from django_tenants.utils import schema_context

from rest_framework import status

from salonDetails.models import SalonDetails
from subscription.models import SubscriptionPlan
from tenant.models import Domain, Tenant
from tenant.serializers import TenantDomainSerializer
from tenant.views import create_tenant_and_domain
from utils.custom_exception import BadRequestException
from utils.testing import TenantAPITestCase


class TenantTestCaseBase(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with schema_context("public"):
            self.salon = SalonDetails.objects.create(
                name="Bella Salon", status="active"
            )


class TenantDomainSerializerTests(TenantTestCaseBase):
    def test_a_uuid_salon_id_is_accepted(self):
        """
        SalonDetails.id is a UUID; the field used to be an IntegerField, so no
        real salon id could ever be submitted.
        """
        serializer = TenantDomainSerializer(
            data={
                "tenant_name": "bella",
                "domain_name": "bella.localhost",
                "salon": str(self.salon.id),
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_a_non_uuid_salon_id_is_rejected(self):
        serializer = TenantDomainSerializer(
            data={
                "tenant_name": "bella",
                "domain_name": "bella.localhost",
                "salon": "123",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("salon", serializer.errors)


class CreateTenantAndDomainTests(TenantTestCaseBase):
    def test_a_missing_trial_plan_is_reported_not_half_applied(self):
        """
        With no trial plan seeded the helper used to raise DoesNotExist after
        deciding to build the tenant. It now refuses before writing anything.
        """
        with schema_context("public"):
            SubscriptionPlan.objects.filter(
                plan_type="free", interval="trial"
            ).delete()

            with self.assertRaises(BadRequestException):
                create_tenant_and_domain(
                    "newsalon", "newsalon.localhost", self.salon.id
                )

            self.assertFalse(
                Tenant.objects.filter(schema_name="newsalon").exists()
            )

    def test_an_unknown_salon_is_reported(self):
        with schema_context("public"):
            with self.assertRaises(BadRequestException):
                create_tenant_and_domain(
                    "newsalon",
                    "newsalon.localhost",
                    "11111111-1111-1111-1111-111111111111",
                )

    def test_a_failed_schema_build_leaves_no_orphan_tenant(self):
        """
        Tenant row, domain and schema have to appear together - a tenant whose
        schema creation failed is unusable but still occupies the slug.
        """
        with schema_context("public"):
            SubscriptionPlan.objects.get_or_create(
                plan_type="free", interval="trial", defaults={"name": "Trial"}
            )

            with patch(
                "tenant.views.call_command", side_effect=RuntimeError("boom")
            ):
                with self.assertRaises(RuntimeError):
                    create_tenant_and_domain(
                        "brokensalon", "brokensalon.localhost", self.salon.id
                    )

            self.assertFalse(
                Tenant.objects.filter(schema_name="brokensalon").exists()
            )
            self.assertFalse(
                Domain.objects.filter(domain="brokensalon.localhost").exists()
            )


class TenantApiPermissionTests(TenantTestCaseBase):
    """The tenant admin API is reserved for a public-schema superuser."""

    def test_a_tenant_admin_cannot_list_tenants(self):
        self.authenticate(self.admin)

        response = self.client.get(reverse("Tenant-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_tenant_admin_cannot_create_a_tenant(self):
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("Tenant-create-tenant"),
            {
                "tenant_name": "sneaky",
                "domain_name": "sneaky.localhost",
                "salon": str(self.salon.id),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        with schema_context("public"):
            self.assertFalse(Tenant.objects.filter(schema_name="sneaky").exists())

    def test_a_tenant_admin_cannot_rename_a_domain(self):
        self.authenticate(self.admin)

        response = self.client.patch(
            reverse("Tenant-update-domain", args=[self.tenant.id]),
            {"domain_name": "hijacked.localhost"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_access_is_refused(self):
        response = self.client.get(reverse("Tenant-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UpdateDomainTests(TenantTestCaseBase):
    """
    Exercises the domain rename logic directly.

    The view used to return None whenever the payload failed validation, which
    Django turns into "view didn't return an HttpResponse" - a 500.
    """

    def setUp(self):
        super().setUp()
        from tenant.views import TenantViewSet

        self.viewset = TenantViewSet()

    def rename(self, tenant, new_domain):
        serializer = TenantDomainSerializer(
            data={
                "tenant_name": "x",
                "domain_name": new_domain,
                "salon": str(self.salon.id),
            }
        )
        serializer.is_valid()
        return self.viewset._rename_primary_domain(
            tenant, new_domain, serializer
        )

    def test_renaming_an_unknown_tenant_is_a_404(self):
        response = self.rename(None, "whatever.localhost")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_domain_already_in_use_is_rejected(self):
        with schema_context("public"):
            other = Tenant.objects.create(
                schema_name="othersalon", name="Other"
            )
            Domain.objects.create(
                tenant=other, domain="taken.localhost", is_primary=True
            )

            response = self.rename(self.tenant, "taken.localhost")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_tenant_with_no_domain_is_a_404(self):
        with schema_context("public"):
            bare = Tenant.objects.create(schema_name="baresalon", name="Bare")

            response = self.rename(bare, "bare.localhost")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_valid_rename_succeeds(self):
        with schema_context("public"):
            response = self.rename(self.tenant, "renamed.localhost")

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(
                Domain.objects.filter(domain="renamed.localhost").exists()
            )


class TenantModelTests(TenantTestCaseBase):
    def test_str_includes_the_subscription_status(self):
        self.tenant.name = "Bella"
        self.tenant.subscription_status = "active"

        self.assertEqual(str(self.tenant), "Bella (active)")

    def test_schemas_are_not_dropped_automatically_on_create(self):
        """auto_create_schema is off so tenant creation stays explicit."""
        self.assertFalse(Tenant.auto_create_schema)
