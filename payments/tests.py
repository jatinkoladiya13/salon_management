from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse

from django_tenants.utils import schema_context

from rest_framework import status

from payments.models import PaymentConfiguration, PaymentProvider
from payments.money import from_minor_units, to_minor_units
from utils.testing import TenantAPITestCase


class MoneyConversionTests(TenantAPITestCase):
    """
    Stored amounts are in major units; gateways bill in minor units. Getting
    this wrong is a direct over- or under-charge, so the conversion is pinned
    down here.
    """

    def test_major_to_minor_keeps_the_paise(self):
        self.assertEqual(to_minor_units(Decimal("20.50")), 2050)
        self.assertEqual(to_minor_units(Decimal("1")), 100)
        self.assertEqual(to_minor_units(Decimal("0.01")), 1)

    def test_the_old_truncation_bug_does_not_return(self):
        """int(Decimal("20.50")) is 20 - a bill of 20 paise instead of 20.50."""
        self.assertNotEqual(to_minor_units(Decimal("20.50")), 20)

    def test_minor_to_major_round_trips(self):
        for amount in ("20.50", "0.01", "1999.99"):
            self.assertEqual(
                from_minor_units(to_minor_units(Decimal(amount))),
                Decimal(amount),
            )

    def test_halves_round_away_from_zero(self):
        self.assertEqual(to_minor_units(Decimal("0.005")), 1)

    def test_zero_decimal_currencies_are_not_scaled(self):
        self.assertEqual(to_minor_units(Decimal("500"), "JPY"), 500)
        self.assertEqual(from_minor_units(500, "JPY"), Decimal("500.00"))

    def test_none_and_zero_are_safe(self):
        self.assertEqual(to_minor_units(None), 0)
        self.assertEqual(from_minor_units(None), Decimal("0.00"))


class PaymentConfigurationModelTests(TenantAPITestCase):
    def test_saving_an_active_config_deactivates_the_others(self):
        with schema_context(self.tenant.schema_name):
            first = PaymentConfiguration.objects.create(
                provider=PaymentProvider.STRIPE, is_active=True
            )
            second = PaymentConfiguration.objects.create(
                provider=PaymentProvider.RAZORPAY, is_active=True
            )

            first.refresh_from_db()
            second.refresh_from_db()
            self.assertFalse(first.is_active)
            self.assertTrue(second.is_active)

    def test_an_inactive_config_leaves_the_active_one_alone(self):
        with schema_context(self.tenant.schema_name):
            active = PaymentConfiguration.objects.create(
                provider=PaymentProvider.STRIPE, is_active=True
            )
            PaymentConfiguration.objects.create(
                provider=PaymentProvider.RAZORPAY, is_active=False
            )

            active.refresh_from_db()
            self.assertTrue(active.is_active)


class PaymentConfigurationApiTests(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with schema_context(self.tenant.schema_name):
            self.config = PaymentConfiguration.objects.create(
                provider=PaymentProvider.RAZORPAY,
                is_active=True,
                currency="INR",
                webhook_secret="whsec-super-secret",
                payment_credentials={
                    "razorpay_key_id": "rzp_test_public",
                    "razorpay_key_secret": "rzp_test_secret_value",
                    "mode": "test",
                },
            )

    def test_gateway_secrets_are_never_returned_by_the_api(self):
        """
        The serializer exposed payment_credentials and webhook_secret verbatim,
        so a single GET handed out the live gateway keys in plaintext.
        """
        self.authenticate(self.admin)

        response = self.client.get(
            reverse("payment-configuration-detail", args=[self.config.id])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = str(response.data)
        self.assertNotIn("rzp_test_secret_value", body)
        self.assertNotIn("whsec-super-secret", body)

    def test_public_identifiers_are_still_visible_and_secrets_are_masked(self):
        self.authenticate(self.admin)

        response = self.client.get(
            reverse("payment-configuration-detail", args=[self.config.id])
        )

        summary = response.data["data"]["payment_credentials_summary"]
        self.assertEqual(summary["razorpay_key_id"], "rzp_test_public")
        self.assertEqual(summary["mode"], "test")
        self.assertEqual(summary["razorpay_key_secret"], "********")

    def test_the_list_endpoint_also_withholds_secrets(self):
        self.authenticate(self.admin)

        response = self.client.get(reverse("payment-configuration-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("rzp_test_secret_value", str(response.data))

    def test_a_customer_cannot_read_payment_configuration(self):
        self.authenticate(self.customer)

        response = self.client.get(reverse("payment-configuration-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_staff_member_cannot_change_payment_configuration(self):
        self.authenticate(self.staff)

        response = self.client.patch(
            reverse("payment-configuration-detail", args=[self.config.id]),
            {"currency": "USD"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_access_is_refused(self):
        response = self.client.get(reverse("payment-configuration-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_credentials_can_still_be_written(self):
        self.authenticate(self.admin)

        with patch("payments.serializers.razorpay.Client") as mock_client:
            mock_client.return_value.payment.all.return_value = {"items": []}

            response = self.client.patch(
                reverse("payment-configuration-detail", args=[self.config.id]),
                {
                    "payment_credentials": {
                        "razorpay_key_id": "rzp_new_public",
                        "razorpay_key_secret": "rzp_new_secret",
                        "mode": "test",
                    }
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.config.refresh_from_db()
            self.assertEqual(
                self.config.payment_credentials["razorpay_key_secret"],
                "rzp_new_secret",
            )

    def test_incomplete_razorpay_credentials_are_rejected(self):
        self.authenticate(self.admin)

        response = self.client.patch(
            reverse("payment-configuration-detail", args=[self.config.id]),
            {"payment_credentials": {"razorpay_key_id": "only-the-public-half"}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_unrelated_patch_does_not_require_resending_credentials(self):
        """
        Validation used to read the provider straight from the payload, so a
        PATCH that only changed the currency skipped credential checks entirely
        (and a PATCH that resent them had no provider to validate against).
        """
        self.authenticate(self.admin)

        response = self.client.patch(
            reverse("payment-configuration-detail", args=[self.config.id]),
            {"currency": "USD"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.config.refresh_from_db()
            self.assertEqual(self.config.currency, "USD")
            self.assertEqual(
                self.config.payment_credentials["razorpay_key_secret"],
                "rzp_test_secret_value",
            )

    def test_branding_details_require_a_name_and_description(self):
        self.authenticate(self.admin)

        response = self.client.patch(
            reverse("payment-configuration-detail", args=[self.config.id]),
            {"branding_details": {"shop_name": "Bella"}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
