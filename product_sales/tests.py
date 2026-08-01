from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from product_sales.models import Invoice


class InvoiceRecalcTotalTests(TestCase):
    def test_recalc_total_uses_decimal_values(self):
        User = get_user_model()
        user = User.objects.create(
            email="invoice-test@example.com",
            username="invoice-test",
            mobile="1234567890",
            password="testpass123",
        )

        invoice = Invoice.objects.create(
            invoice_number="INV-TEST-001",
            user=user,
            payment_method="card",
            payment_status="paid",
            order_status="confirmed",
        )
        invoice.discount = 0.5
        invoice.tax = 0.0
        invoice.recalc_total()

        self.assertEqual(invoice.total_amount, Decimal("-0.50"))
