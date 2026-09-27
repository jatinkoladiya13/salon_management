from types import SimpleNamespace
from unittest.mock import patch

from django.urls import reverse

from django_tenants.utils import schema_context

from rest_framework import status

from subscription.models import SubscriptionPlan
from subscription.utils import (
    cancel_subscriptions,
    find_plan_by_price,
    get_active_subscription,
)
from utils.testing import TenantAPITestCase


class SubscriptionTestCase(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with schema_context("public"):
            self.trial_plan = SubscriptionPlan.objects.create(
                name="Trial", plan_type="free", interval="trial"
            )
            self.pro_plan = SubscriptionPlan.objects.create(
                name="Pro Monthly", plan_type="pro", interval="month"
            )


class PlanLookupTests(SubscriptionTestCase):
    def test_a_stripe_price_string_does_not_raise(self):
        """
        stripe_price_id is djstripe's integer key. Filtering it with a Stripe
        price string ("price_123") raised ValueError, which surfaced as a 500
        rather than "invalid plan".
        """
        self.assertIsNone(find_plan_by_price("price_does_not_exist"))

    def test_a_numeric_id_that_matches_nothing_returns_none(self):
        self.assertIsNone(find_plan_by_price("999999"))

    def test_an_empty_identifier_returns_none(self):
        self.assertIsNone(find_plan_by_price(None))
        self.assertIsNone(find_plan_by_price(""))

    def test_inactive_plans_are_excluded_by_default(self):
        with schema_context("public"):
            self.pro_plan.is_active = False
            self.pro_plan.save(update_fields=["is_active"])

        self.assertIsNone(find_plan_by_price("1"))


class OwnSubscriptionApiTests(SubscriptionTestCase):
    def test_a_signed_in_user_can_read_their_workspace_subscription(self):
        self.authenticate(self.customer)

        response = self.client.get(reverse("get-own-subscription"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["data"]["schema_name"], self.tenant.schema_name
        )

    def test_anonymous_access_is_refused(self):
        response = self.client.get(reverse("get-own-subscription"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CancelSubscriptionApiTests(SubscriptionTestCase):
    def test_a_customer_cannot_cancel_the_workspace_subscription(self):
        self.authenticate(self.customer)

        response = self.client.get(reverse("cancel-subscription"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_trial_plan_has_nothing_to_cancel(self):
        self.tenant.subscription_plan = self.trial_plan
        self.tenant.subscription_status = "active"
        self.tenant.save(
            update_fields=["subscription_plan", "subscription_status"]
        )

        self.authenticate(self.admin)
        response = self.client.get(reverse("cancel-subscription"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_expired_subscription_has_nothing_to_cancel(self):
        self.tenant.subscription_plan = self.pro_plan
        self.tenant.subscription_status = "expired"
        self.tenant.save(
            update_fields=["subscription_plan", "subscription_status"]
        )

        self.authenticate(self.admin)
        response = self.client.get(reverse("cancel-subscription"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_paid_subscription_is_cancelled_through_stripe(self):
        self.tenant.subscription_plan = self.pro_plan
        self.tenant.subscription_status = "active"
        self.tenant.stripe_subscription_id = "sub_123"
        self.tenant.save(
            update_fields=[
                "subscription_plan",
                "subscription_status",
                "stripe_subscription_id",
            ]
        )

        self.authenticate(self.admin)
        with patch(
            "subscription.views.cancel_subscriptions", return_value=True
        ) as mock_cancel:
            response = self.client.get(reverse("cancel-subscription"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_cancel.assert_called_once()


class UpgradeSubscriptionApiTests(SubscriptionTestCase):
    def setUp(self):
        super().setUp()
        self.tenant.subscription_plan = self.pro_plan
        self.tenant.subscription_status = "active"
        self.tenant.stripe_customer_id = "cus_123"
        self.tenant.save(
            update_fields=[
                "subscription_plan",
                "subscription_status",
                "stripe_customer_id",
            ]
        )

    def test_a_missing_price_id_is_rejected(self):
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("upgrade-subscription"), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_unknown_price_reports_an_invalid_plan_not_a_crash(self):
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("upgrade-subscription"),
            {"price_id": "price_nope"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid subscription plan", str(response.data["message"]))

    def test_a_customer_cannot_upgrade_the_workspace_plan(self):
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("upgrade-subscription"),
            {"price_id": "price_123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_active_stripe_subscription_is_reported_cleanly(self):
        """
        get_active_subscription() returns None when the Stripe call fails, and
        the view used to subscript it straight away (TypeError -> 500).
        """
        self.authenticate(self.admin)

        with patch(
            "subscription.views.find_plan_by_price", return_value=self.pro_plan
        ), patch(
            "subscription.views.get_active_subscription", return_value=None
        ):
            response = self.client.post(
                reverse("upgrade-subscription"),
                {"price_id": "1"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_declined_upgrade_returns_a_bad_request_not_a_server_error(self):
        """
        When Stripe produces no invoice URL the method used to fall off the
        end, which Django reports as "view didn't return an HttpResponse".
        """
        self.authenticate(self.admin)
        other_plan = None
        with schema_context("public"):
            other_plan = SubscriptionPlan.objects.create(
                name="Enterprise Monthly",
                plan_type="enterprise",
                interval="month",
            )

        with patch(
            "subscription.views.find_plan_by_price", return_value=other_plan
        ), patch(
            "subscription.views.get_active_subscription",
            return_value={"data": [{"id": "sub_123"}]},
        ), patch(
            "subscription.views.upgrade_subscription", return_value=None
        ):
            response = self.client.post(
                reverse("upgrade-subscription"),
                {"price_id": "1"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upgrading_to_the_same_plan_is_refused(self):
        self.authenticate(self.admin)

        with patch(
            "subscription.views.find_plan_by_price", return_value=self.pro_plan
        ):
            response = self.client.post(
                reverse("upgrade-subscription"),
                {"price_id": "1"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already have same", str(response.data["message"]))

    def test_switching_billing_interval_is_refused(self):
        self.authenticate(self.admin)
        with schema_context("public"):
            yearly = SubscriptionPlan.objects.create(
                name="Pro Yearly", plan_type="pro", interval="year"
            )

        with patch(
            "subscription.views.find_plan_by_price", return_value=yearly
        ):
            response = self.client.post(
                reverse("upgrade-subscription"),
                {"price_id": "1"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("same interval", str(response.data["message"]))


class FakeSubscriptionList:
    """
    Stands in for a Stripe ListObject: subscriptable *and* attribute-accessible,
    exactly like the real thing the helper reads both ways.
    """

    def __init__(self, *subscription_ids):
        self.data = [SimpleNamespace(id=sid) for sid in subscription_ids]

    def __getitem__(self, key):
        if key == "data":
            return self.data
        raise KeyError(key)


class StripeHelperTests(SubscriptionTestCase):
    def test_the_resolved_subscription_id_is_persisted(self):
        """
        The helper assigned to ``tenant.stipe_subscription_id`` - a typo that
        set a stray attribute, so the id was never written to the row.
        """
        self.tenant.stripe_customer_id = "cus_123"
        self.tenant.save(update_fields=["stripe_customer_id"])

        with patch("subscription.utils.stripe") as mock_stripe:
            mock_stripe.Subscription.list.return_value = FakeSubscriptionList(
                "sub_persisted"
            )

            get_active_subscription("cus_123", self.tenant)

        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_subscription_id, "sub_persisted")

    def test_no_customer_id_short_circuits(self):
        self.assertIsNone(get_active_subscription(None, self.tenant))

    def test_a_stripe_failure_is_swallowed_and_reported_as_none(self):
        with patch("subscription.utils.stripe") as mock_stripe:
            mock_stripe.Subscription.list.side_effect = Exception("network down")

            self.assertIsNone(get_active_subscription("cus_123", self.tenant))

    def test_cancel_returns_false_when_stripe_fails(self):
        with patch("subscription.utils.stripe") as mock_stripe:
            mock_stripe.Subscription.modify.side_effect = Exception("nope")

            self.assertFalse(cancel_subscriptions("sub_123", period_end=True))


class SubscriptionPlanAdminApiTests(SubscriptionTestCase):
    def test_a_tenant_admin_cannot_manage_global_plans(self):
        """Plans are platform-wide, so only a public-schema superuser may edit."""
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("subscriptionplan-list"),
            {"name": "Sneaky Plan", "plan_type": "pro", "interval": "month"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_tenant_admin_cannot_list_global_plans(self):
        self.authenticate(self.admin)

        response = self.client.get(reverse("subscriptionplan-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class InvoiceIsolationTests(SubscriptionTestCase):
    def test_a_date_filter_does_not_bypass_the_tenant_filter(self):
        """
        The customer filter sat after an early ``return`` in the date-filter
        branch, so a tenant admin who passed start_date/end_date received every
        customer's invoices.
        """
        self.tenant.stripe_customer_id = "cus_mine"
        self.tenant.save(update_fields=["stripe_customer_id"])

        self.authenticate(self.admin)

        with patch("subscription.views.stripe") as mock_stripe:
            mock_stripe.Invoice.list.return_value = SimpleNamespace(
                auto_paging_iter=lambda: iter([])
            )

            response = self.client.get(
                reverse("subscription-invoice-list"),
                {"start_date": "2020-01-01", "end_date": "2030-01-01"},
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["results"], [])

    def test_a_malformed_date_is_a_bad_request(self):
        self.tenant.stripe_customer_id = "cus_mine"
        self.tenant.save(update_fields=["stripe_customer_id"])

        self.authenticate(self.admin)

        with patch("subscription.views.stripe") as mock_stripe:
            mock_stripe.Invoice.list.return_value = SimpleNamespace(
                auto_paging_iter=lambda: iter([])
            )

            response = self.client.get(
                reverse("subscription-invoice-list"),
                {"start_date": "not-a-date", "end_date": "2030-01-01"},
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_tenant_with_no_stripe_customer_sees_nothing(self):
        self.tenant.stripe_customer_id = None
        self.tenant.save(update_fields=["stripe_customer_id"])

        self.authenticate(self.admin)

        with patch("subscription.views.stripe") as mock_stripe:
            mock_stripe.Invoice.list.return_value = SimpleNamespace(
                auto_paging_iter=lambda: iter([])
            )

            response = self.client.get(reverse("subscription-invoice-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["results"], [])

    def test_a_customer_cannot_read_workspace_invoices(self):
        self.authenticate(self.customer)

        response = self.client.get(reverse("subscription-invoice-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
