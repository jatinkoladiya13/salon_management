from django.urls import reverse

from django_tenants.utils import schema_context

from rest_framework import status

from salonDetails.models import SalonDetails
from salonDetails.serializers import (
    SalonDetailsCreateSerializer,
    SalongDetailsRetrieveSerializer,
)
from utils.testing import TenantAPITestCase


class SalonDetailsTestCase(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with schema_context("public"):
            self.salon = SalonDetails.objects.create(
                name="Bella Salon",
                organization_email="hello@bella.test",
                phone_number="+919876543210",
                status="active",
                city="Mumbai",
            )


class SalonDetailsRetrieveSerializerTests(SalonDetailsTestCase):
    def test_the_retrieve_serializer_renders_without_an_attribute_error(self):
        """
        The serializer declared ``tenant_for_salon``, which is not a field or
        reverse accessor on SalonDetails - Tenant.salonDetails uses
        related_name="salong_for_tenant". Every retrieve raised AttributeError
        before the fix.
        """
        with schema_context("public"):
            data = SalongDetailsRetrieveSerializer(self.salon).data

        self.assertEqual(data["name"], "Bella Salon")
        self.assertIn("salong_for_tenant", data)

    def test_the_linked_tenant_is_exposed_when_there_is_one(self):
        with schema_context("public"):
            self.tenant.salonDetails = self.salon
            self.tenant.save(update_fields=["salonDetails"])

            data = SalongDetailsRetrieveSerializer(
                SalonDetails.objects.get(pk=self.salon.pk)
            ).data

        self.assertIsNotNone(data["salong_for_tenant"])
        self.assertEqual(
            data["salong_for_tenant"]["schema_name"], self.tenant.schema_name
        )


class SalonDetailsApiPermissionTests(SalonDetailsTestCase):
    def test_anonymous_access_is_refused(self):
        response = self.client.get(reverse("salonDetails-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_tenant_customer_cannot_list_salons(self):
        """
        Salon records are cross-tenant data held in the public schema, so the
        endpoint is restricted to a public-schema superuser.
        """
        self.authenticate(self.customer)

        response = self.client.get(reverse("salonDetails-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_tenant_admin_cannot_list_salons_either(self):
        self.authenticate(self.admin)

        response = self.client.get(reverse("salonDetails-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_tenant_admin_cannot_delete_a_salon(self):
        self.authenticate(self.admin)

        response = self.client.delete(
            reverse("salonDetails-detail", args=[self.salon.id])
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        with schema_context("public"):
            self.assertTrue(
                SalonDetails.objects.filter(id=self.salon.id).exists()
            )


class SalonDetailsValidationTests(SalonDetailsTestCase):
    class FakeUpload:
        def __init__(self, name, size):
            self.name = name
            self.size = size

    def test_an_oversized_logo_is_rejected(self):
        serializer = SalonDetailsCreateSerializer()

        with self.assertRaises(Exception):
            serializer.validate_company_logo(
                self.FakeUpload("logo.png", 2 * 1024 * 1024)
            )

    def test_a_non_image_logo_is_rejected(self):
        serializer = SalonDetailsCreateSerializer()

        with self.assertRaises(Exception):
            serializer.validate_company_logo(self.FakeUpload("payload.svg", 100))

    def test_a_valid_logo_is_accepted(self):
        serializer = SalonDetailsCreateSerializer()
        upload = self.FakeUpload("logo.png", 1000)

        self.assertIs(serializer.validate_company_logo(upload), upload)


class SalonDetailsModelTests(SalonDetailsTestCase):
    def test_the_slug_is_generated_from_the_name(self):
        with schema_context("public"):
            self.salon.refresh_from_db()
            self.assertTrue(self.salon.slug)

    def test_str_falls_back_to_the_id_when_unnamed(self):
        with schema_context("public"):
            unnamed = SalonDetails.objects.create(status="active")

            self.assertEqual(str(unnamed), str(unnamed.id))
