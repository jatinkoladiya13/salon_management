from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.urls import reverse

from django_tenants.utils import schema_context

from rest_framework import status

from payments.models import PaymentConfiguration, PaymentProvider
from product_sales.models import (
    CartItem,
    Invoice,
    Product,
    ProductCategory,
    build_invoice_number,
)
from utils.testing import TenantAPITestCase


class ProductCheckoutTestCase(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with schema_context(self.tenant.schema_name):
            self.category = ProductCategory.objects.create(name="Hair Care")
            self.shampoo = Product.objects.create(
                name="Shampoo",
                product_category=self.category,
                current_stock=10,
                purchase_price=Decimal("100.00"),
                selling_price=Decimal("150.50"),
            )
            self.cart_item = CartItem.objects.create(
                user=self.customer,
                product=self.shampoo,
                quantity=2,
                price=Decimal("150.50"),
            )

    def configure(self, provider, credentials=None):
        with schema_context(self.tenant.schema_name):
            PaymentConfiguration.objects.all().delete()
            return PaymentConfiguration.objects.create(
                provider=provider,
                is_active=True,
                currency="INR",
                payment_credentials=credentials or {},
            )


class ProductCheckoutSessionTests(ProductCheckoutTestCase):
    STRIPE_CREDENTIALS = {
        "stripe_public_key": "pk_test",
        "stripe_secret_key": "sk_test",
        "mode": "test",
    }
    RAZORPAY_CREDENTIALS = {
        "razorpay_key_id": "rzp_public",
        "razorpay_key_secret": "rzp_secret",
        "mode": "test",
    }

    def test_stripe_line_items_are_priced_in_the_smallest_currency_unit(self):
        """
        The unit amount used to be ``int(cart_item.price)``, which truncated
        150.50 rupees to 150 *paise* - a bill of about one hundredth of the
        real price.
        """
        self.configure(PaymentProvider.STRIPE, self.STRIPE_CREDENTIALS)
        self.authenticate(self.customer)

        with patch(
            "checkout.views.StripePaymentService.create_checkout_session"
        ) as mock_session:
            mock_session.return_value = SimpleNamespace(
                url="https://checkout.example/session"
            )

            response = self.client.post(
                reverse("product-checkout-session"),
                {"cart_item_ids": [str(self.cart_item.id)]},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        line_items = mock_session.call_args.kwargs["line_items"]
        self.assertEqual(line_items[0]["price_data"]["unit_amount"], 15050)
        self.assertEqual(line_items[0]["quantity"], 2)

    def test_razorpay_order_stores_the_total_in_major_units(self):
        self.configure(PaymentProvider.RAZORPAY, self.RAZORPAY_CREDENTIALS)
        self.authenticate(self.customer)

        with patch(
            "checkout.views.RazorpayPaymentService.create_checkout_session"
        ) as mock_order:
            # 2 x 150.50 rupees = 30100 paise
            mock_order.return_value = {
                "id": "order_ABC123",
                "amount": 30100,
                "currency": "INR",
            }

            response = self.client.post(
                reverse("product-checkout-session"),
                {"cart_item_ids": [str(self.cart_item.id)]},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            invoice = Invoice.objects.get(razorpay_order_id="order_ABC123")
            self.assertEqual(invoice.total_amount, Decimal("301.00"))
            self.assertEqual(invoice.payment_status, "unpaid")

    def test_razorpay_order_records_the_lines_that_were_ordered(self):
        """
        The lines used to be rebuilt from the live cart when the webhook
        arrived, so anything added in between was shipped against a total the
        customer never paid.
        """
        self.configure(PaymentProvider.RAZORPAY, self.RAZORPAY_CREDENTIALS)
        self.authenticate(self.customer)

        with patch(
            "checkout.views.RazorpayPaymentService.create_checkout_session"
        ) as mock_order:
            mock_order.return_value = {
                "id": "order_ABC123",
                "amount": 30100,
                "currency": "INR",
            }

            self.client.post(
                reverse("product-checkout-session"),
                {"cart_item_ids": [str(self.cart_item.id)]},
                format="json",
            )

        with schema_context(self.tenant.schema_name):
            invoice = Invoice.objects.get(razorpay_order_id="order_ABC123")
            self.assertEqual(invoice.items.count(), 1)
            self.assertEqual(invoice.items.get().quantity, 2)
            # The units are reserved for the duration of the payment.
            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 8)

    def test_checkout_is_refused_when_the_stock_has_gone(self):
        self.configure(PaymentProvider.STRIPE, self.STRIPE_CREDENTIALS)
        with schema_context(self.tenant.schema_name):
            self.shampoo.current_stock = 1
            self.shampoo.save(update_fields=["current_stock"])

        self.authenticate(self.customer)
        response = self.client.post(
            reverse("product-checkout-session"),
            {"cart_item_ids": [str(self.cart_item.id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_another_users_cart_item_cannot_be_checked_out(self):
        self.configure(PaymentProvider.STRIPE, self.STRIPE_CREDENTIALS)
        self.authenticate(self.staff)

        response = self.client.post(
            reverse("product-checkout-session"),
            {"cart_item_ids": [str(self.cart_item.id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_checkout_without_a_payment_configuration_is_a_bad_request(self):
        with schema_context(self.tenant.schema_name):
            PaymentConfiguration.objects.all().delete()

        self.authenticate(self.customer)
        response = self.client.post(
            reverse("product-checkout-session"),
            {"cart_item_ids": [str(self.cart_item.id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_unsupported_provider_reports_a_bad_request_not_a_crash(self):
        """
        PayPal is a valid PaymentProvider choice with no checkout
        implementation. The view used to fall off the end and return None,
        which Django turns into a 500.
        """
        self.configure(PaymentProvider.PAYPAL)
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("product-checkout-session"),
            {"cart_item_ids": [str(self.cart_item.id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("paypal", str(response.data["message"]).lower())

    def test_an_empty_cart_item_list_is_rejected(self):
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("product-checkout-session"),
            {"cart_item_ids": []},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_checkout_is_refused(self):
        response = self.client.post(
            reverse("product-checkout-session"),
            {"cart_item_ids": [str(self.cart_item.id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class VerifyRazorpayPaymentTests(ProductCheckoutTestCase):
    def setUp(self):
        super().setUp()
        self.configure(
            PaymentProvider.RAZORPAY,
            {
                "razorpay_key_id": "rzp_public",
                "razorpay_key_secret": "rzp_secret",
                "mode": "test",
            },
        )
        with schema_context(self.tenant.schema_name):
            self.invoice = Invoice.objects.create(
                invoice_number=build_invoice_number(),
                user=self.customer,
                razorpay_order_id="order_ABC123",
                payment_status="unpaid",
                total_amount=Decimal("301.00"),
            )

    def payload(self, **overrides):
        data = {
            "razorpay_order_id": "order_ABC123",
            "razorpay_payment_id": "pay_XYZ789",
            "razorpay_signature": "signature",
        }
        data.update(overrides)
        return data

    def test_a_verified_signature_marks_the_invoice_paid(self):
        self.authenticate(self.customer)

        with patch("checkout.views.razorpay.Client") as mock_client:
            mock_client.return_value.utility.verify_payment_signature.return_value = True

            response = self.client.post(
                reverse("verify-razorpay-payment"), self.payload(), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.invoice.refresh_from_db()
            self.assertEqual(self.invoice.payment_status, "paid")
            self.assertEqual(self.invoice.razorpay_payment_id, "pay_XYZ789")

    def test_an_unknown_order_returns_404_instead_of_a_server_error(self):
        """
        The lookup used .get(), so an unknown order id raised DoesNotExist and
        the "not found" branch underneath it was unreachable.
        """
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("verify-razorpay-payment"),
            self.payload(razorpay_order_id="order_NOPE"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_another_users_order_cannot_be_verified(self):
        self.authenticate(self.staff)

        response = self.client.post(
            reverse("verify-razorpay-payment"), self.payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_parameters_are_rejected(self):
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("verify-razorpay-payment"),
            {"razorpay_order_id": "order_ABC123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verifying_twice_is_refused(self):
        with schema_context(self.tenant.schema_name):
            self.invoice.payment_status = "paid"
            self.invoice.save(update_fields=["payment_status"])

        self.authenticate(self.customer)
        response = self.client.post(
            reverse("verify-razorpay-payment"), self.payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SubscriptionCheckoutTests(TenantAPITestCase):
    def test_a_missing_price_id_is_rejected(self):
        self.authenticate(self.admin)

        response = self.client.post(
            reverse("create-checkout-session"), {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_active_tenant_without_a_plan_does_not_crash(self):
        """
        subscription_plan is nullable, and dereferencing .interval on it raised
        AttributeError for any tenant whose status was active but whose plan
        had been cleared.
        """
        self.tenant.subscription_status = "active"
        self.tenant.subscription_plan = None
        self.tenant.save(
            update_fields=["subscription_status", "subscription_plan"]
        )

        self.authenticate(self.admin)
        response = self.client.post(
            reverse("create-checkout-session"),
            {"price_id": "price_unknown"},
            format="json",
        )

        # Reaches the plan lookup and reports it cleanly.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid subscription plan", str(response.data["message"]))

    def test_a_customer_cannot_start_a_subscription_checkout(self):
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("create-checkout-session"),
            {"price_id": "price_123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
