from django.contrib.auth import get_user_model
from django.test import TestCase

from product_sales.models import CartItem, Invoice, InvoiceItem, Product, ProductCategory
from webhook_handler.views import RazorpayWebhookView


class RazorpayWebhookViewTests(TestCase):
    def test_create_invoice_items_from_cart_items(self):
        User = get_user_model()
        user = User.objects.create(username="testuser", email="test@example.com")

        category = ProductCategory.objects.create(name="Test Category")
        product = Product.objects.create(
            name="Test Product",
            product_category=category,
            current_stock=10,
            purchase_price="10.00",
            selling_price="20.00",
        )
        invoice = Invoice.objects.create(
            invoice_number="INV-TEST-001",
            user=user,
            phone="1234567890",
            shipping_address="Test address",
            payment_method="card",
            payment_status="paid",
            order_status="confirmed",
            total_amount="100.00",
        )
        CartItem.objects.create(user=user, product=product, quantity=2, price="5.00")

        view = RazorpayWebhookView()
        view.create_invoice_items_from_invoice(invoice)

        self.assertEqual(invoice.items.count(), 1)
        self.assertEqual(invoice.items.get().quantity, 2)
        self.assertEqual(CartItem.objects.filter(user=user).count(), 0)
