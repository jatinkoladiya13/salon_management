import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from django_tenants.utils import schema_context

from rest_framework import status

from payments.models import PaymentConfiguration, PaymentProvider
from product_sales.models import (
    CartItem,
    Invoice,
    InvoiceItem,
    Product,
    ProductCategory,
    build_invoice_number,
)
from utils.testing import TenantAPITestCase
from webhook_handler.views import RazorpayWebhookView, StripeWebhookView


class WebhookTestCase(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with schema_context(self.tenant.schema_name):
            self.category = ProductCategory.objects.create(name="Hair Care")
            self.shampoo = Product.objects.create(
                name="Shampoo",
                product_category=self.category,
                current_stock=10,
                purchase_price=Decimal("100.00"),
                selling_price=Decimal("150.00"),
            )
            self.config = PaymentConfiguration.objects.create(
                provider=PaymentProvider.RAZORPAY,
                is_active=True,
                currency="INR",
                webhook_secret="whsec-test",
                payment_credentials={
                    "razorpay_key_id": "rzp_public",
                    "razorpay_key_secret": "rzp_secret",
                    "mode": "test",
                },
            )

    def razorpay_url(self):
        return reverse("razorpay_webhook", args=[self.tenant.id])

    def payment_event(self, event, order_id, payment_id="pay_1"):
        return {
            "event": event,
            "payload": {
                "payment": {
                    "entity": {"id": payment_id, "order_id": order_id}
                }
            },
        }


class SubscriptionExpiryTests(TenantAPITestCase):
    def test_a_yearly_plan_expires_in_a_year_not_a_month(self):
        """
        SubscriptionPlan uses "year"; the handler compared against "yearly", so
        annual subscribers were silently cut off after 30 days.
        """
        view = StripeWebhookView()

        expiry = view.get_expiry_date("year")

        self.assertGreater(expiry, timezone.now() + timedelta(days=360))

    def test_a_monthly_plan_expires_in_a_month(self):
        view = StripeWebhookView()

        expiry = view.get_expiry_date("month")

        self.assertLess(expiry, timezone.now() + timedelta(days=31))
        self.assertGreater(expiry, timezone.now() + timedelta(days=29))

    def test_the_expiry_is_timezone_aware(self):
        """
        subscription_end_date is a DateTimeField compared against
        timezone.now() during authentication; a bare date is not comparable.
        """
        expiry = StripeWebhookView().get_expiry_date("month")

        self.assertIsNotNone(expiry.tzinfo)


class RazorpayWebhookTests(WebhookTestCase):
    def post_event(self, payload):
        with patch("webhook_handler.views.razorpay.Client") as mock_client:
            mock_client.return_value.utility.verify_webhook_signature.return_value = True

            return self.client.post(
                self.razorpay_url(),
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE="signature",
            )

    def make_order(self, order_id="order_1", with_items=True):
        with schema_context(self.tenant.schema_name):
            invoice = Invoice.objects.create(
                invoice_number=build_invoice_number(),
                user=self.customer,
                razorpay_order_id=order_id,
                payment_status="unpaid",
                total_amount=Decimal("300.00"),
            )
            if with_items:
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=self.shampoo,
                    quantity=2,
                    price=Decimal("150.00"),
                )
            return invoice

    def test_a_captured_payment_marks_the_order_paid_and_confirmed(self):
        invoice = self.make_order()

        response = self.post_event(
            self.payment_event("payment.captured", "order_1")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            invoice.refresh_from_db()
            self.assertEqual(invoice.payment_status, "paid")
            self.assertEqual(invoice.order_status, "confirmed")
            self.assertEqual(invoice.razorpay_payment_id, "pay_1")

    def test_a_captured_payment_clears_the_matching_cart_items(self):
        self.make_order()
        with schema_context(self.tenant.schema_name):
            CartItem.objects.create(
                user=self.customer,
                product=self.shampoo,
                quantity=2,
                price=Decimal("150.00"),
            )

        self.post_event(self.payment_event("payment.captured", "order_1"))

        with schema_context(self.tenant.schema_name):
            self.assertFalse(
                CartItem.objects.filter(user=self.customer).exists()
            )

    def test_redelivering_a_captured_event_does_not_duplicate_lines(self):
        """
        Razorpay retries webhooks; the handler has to be idempotent or the
        customer is billed once and charged stock twice.
        """
        invoice = self.make_order()

        self.post_event(self.payment_event("payment.captured", "order_1"))
        self.post_event(self.payment_event("payment.captured", "order_1"))

        with schema_context(self.tenant.schema_name):
            invoice.refresh_from_db()
            self.assertEqual(invoice.items.count(), 1)
            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 8)

    def test_a_failed_payment_releases_the_reserved_stock(self):
        self.make_order()
        with schema_context(self.tenant.schema_name):
            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 8)

        response = self.post_event(
            self.payment_event("payment.failed", "order_1")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.assertFalse(
                Invoice.objects.filter(razorpay_order_id="order_1").exists()
            )
            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 10)

    def test_a_late_failure_never_deletes_a_paid_order(self):
        """
        Razorpay can deliver payment.failed for an earlier attempt after a
        later one succeeded. Deleting unconditionally destroyed the record of a
        real purchase.
        """
        invoice = self.make_order()
        self.post_event(self.payment_event("payment.captured", "order_1"))

        self.post_event(self.payment_event("payment.failed", "order_1"))

        with schema_context(self.tenant.schema_name):
            invoice.refresh_from_db()
            self.assertEqual(invoice.payment_status, "paid")

    def test_an_invalid_signature_is_rejected(self):
        self.make_order()

        with patch("webhook_handler.views.razorpay") as mock_razorpay:
            mock_razorpay.errors.SignatureVerificationError = Exception
            mock_razorpay.Client.return_value.utility.verify_webhook_signature.side_effect = (
                Exception("bad signature")
            )

            response = self.client.post(
                self.razorpay_url(),
                data=json.dumps(
                    self.payment_event("payment.captured", "order_1")
                ),
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE="wrong",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        with schema_context(self.tenant.schema_name):
            self.assertEqual(
                Invoice.objects.get(razorpay_order_id="order_1").payment_status,
                "unpaid",
            )

    def test_an_unknown_tenant_is_rejected(self):
        response = self.client.post(
            reverse(
                "razorpay_webhook",
                args=["11111111-1111-1111-1111-111111111111"],
            ),
            data=json.dumps(self.payment_event("payment.captured", "order_1")),
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="signature",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_event_for_an_unknown_order_is_acknowledged_quietly(self):
        response = self.post_event(
            self.payment_event("payment.captured", "order_does_not_exist")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RazorpayInvoiceItemFallbackTests(WebhookTestCase):
    def test_a_legacy_order_without_lines_falls_back_to_the_cart(self):
        """
        Orders created before the lines were snapshotted at checkout must not
        be settled as empty invoices.
        """
        with schema_context(self.tenant.schema_name):
            invoice = Invoice.objects.create(
                invoice_number=build_invoice_number(),
                user=self.customer,
                payment_status="paid",
                total_amount=Decimal("300.00"),
            )
            CartItem.objects.create(
                user=self.customer,
                product=self.shampoo,
                quantity=2,
                price=Decimal("150.00"),
            )

            RazorpayWebhookView().create_invoice_items_from_invoice(invoice)

            self.assertEqual(invoice.items.count(), 1)
            self.assertEqual(invoice.items.get().quantity, 2)
            self.assertFalse(
                CartItem.objects.filter(user=self.customer).exists()
            )

    def test_existing_lines_are_left_alone(self):
        with schema_context(self.tenant.schema_name):
            invoice = Invoice.objects.create(
                invoice_number=build_invoice_number(),
                user=self.customer,
                payment_status="paid",
            )
            InvoiceItem.objects.create(
                invoice=invoice,
                product=self.shampoo,
                quantity=1,
                price=Decimal("150.00"),
            )

            RazorpayWebhookView().create_invoice_items_from_invoice(invoice)

            self.assertEqual(invoice.items.count(), 1)
            self.assertEqual(invoice.items.get().quantity, 1)
