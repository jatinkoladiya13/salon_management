from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from django_tenants.utils import schema_context

from rest_framework import status

from product_sales.models import (
    CartItem,
    Invoice,
    InvoiceItem,
    Product,
    ProductCategory,
    build_invoice_number,
)
from utils.testing import TenantAPITestCase


class ProductSalesTestCase(TenantAPITestCase):
    """Shared catalogue fixtures for the product_sales suites."""

    def setUp(self):
        super().setUp()
        with schema_context(self.tenant.schema_name):
            self.category = ProductCategory.objects.create(name="Hair Care")
            self.shampoo = Product.objects.create(
                name="Shampoo",
                product_category=self.category,
                current_stock=10,
                minimum_stock=2,
                purchase_price=Decimal("100.00"),
                selling_price=Decimal("150.50"),
            )


class InvoiceNumberTests(ProductSalesTestCase):
    def test_generated_numbers_are_unique_and_fit_the_column(self):
        """
        The old scheme was a second-resolution timestamp against a unique
        column, so two customers checking out in the same second collided and
        the second checkout failed.
        """
        numbers = {build_invoice_number() for _ in range(200)}

        self.assertEqual(len(numbers), 200)
        for number in numbers:
            self.assertLessEqual(len(number), 20)
            self.assertTrue(number.startswith("INV-"))


class InvoiceItemStockTests(ProductSalesTestCase):
    def make_invoice(self):
        return Invoice.objects.create(
            invoice_number=build_invoice_number(),
            user=self.customer,
            payment_method="card",
        )

    def test_creating_an_item_takes_the_units_out_of_stock(self):
        with schema_context(self.tenant.schema_name):
            invoice = self.make_invoice()

            InvoiceItem.objects.create(
                invoice=invoice,
                product=self.shampoo,
                quantity=3,
                price=Decimal("150.50"),
            )

            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 7)

    def test_selling_more_than_is_in_stock_is_refused(self):
        with schema_context(self.tenant.schema_name):
            invoice = self.make_invoice()

            with self.assertRaises(ValidationError):
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=self.shampoo,
                    quantity=11,
                    price=Decimal("150.50"),
                )

            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 10)

    def test_increasing_a_quantity_only_removes_the_difference(self):
        with schema_context(self.tenant.schema_name):
            invoice = self.make_invoice()
            item = InvoiceItem.objects.create(
                invoice=invoice,
                product=self.shampoo,
                quantity=2,
                price=Decimal("150.50"),
            )

            item.quantity = 5
            item.save()

            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 5)

    def test_deleting_an_item_returns_the_units_to_stock(self):
        with schema_context(self.tenant.schema_name):
            invoice = self.make_invoice()
            item = InvoiceItem.objects.create(
                invoice=invoice,
                product=self.shampoo,
                quantity=4,
                price=Decimal("150.50"),
            )

            item.delete()

            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 10)

    def test_total_is_recalculated_from_the_items(self):
        with schema_context(self.tenant.schema_name):
            invoice = self.make_invoice()
            invoice.discount = Decimal("50.00")
            invoice.tax = Decimal("10.00")
            invoice.save()

            InvoiceItem.objects.create(
                invoice=invoice,
                product=self.shampoo,
                quantity=2,
                price=Decimal("150.50"),
            )

            invoice.refresh_from_db()
            # 2 x 150.50 - 50.00 + 10.00
            self.assertEqual(invoice.total_amount, Decimal("261.00"))

    def test_recalc_total_handles_non_decimal_discounts(self):
        with schema_context(self.tenant.schema_name):
            invoice = self.make_invoice()
            invoice.discount = 0.5
            invoice.tax = 0.0

            invoice.recalc_total()

            self.assertEqual(invoice.total_amount, Decimal("-0.50"))


class CartItemApiTests(ProductSalesTestCase):
    def test_a_customer_can_add_a_product_to_their_cart(self):
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("cart-item-list"),
            {"product": str(self.shampoo.id), "quantity": 2},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        with schema_context(self.tenant.schema_name):
            item = CartItem.objects.get(user=self.customer)
            self.assertEqual(item.quantity, 2)
            self.assertEqual(item.price, self.shampoo.selling_price)

    def test_adding_more_than_the_available_stock_is_refused(self):
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("cart-item-list"),
            {"product": str(self.shampoo.id), "quantity": 50},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_customer_only_sees_their_own_cart(self):
        with schema_context(self.tenant.schema_name):
            CartItem.objects.create(
                user=self.staff, product=self.shampoo, quantity=1, price=Decimal("150.50")
            )
            CartItem.objects.create(
                user=self.customer, product=self.shampoo, quantity=3, price=Decimal("150.50")
            )

        self.authenticate(self.customer)
        response = self.client.get(reverse("cart-item-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["data"]["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], 3)

    def test_a_customer_can_remove_their_own_cart_item(self):
        with schema_context(self.tenant.schema_name):
            item = CartItem.objects.create(
                user=self.customer, product=self.shampoo, quantity=1, price=Decimal("150.50")
            )

        self.authenticate(self.customer)
        response = self.client.delete(
            reverse("cart-item-detail", args=[item.id])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.assertFalse(CartItem.objects.filter(id=item.id).exists())

    def test_a_customer_cannot_touch_another_users_cart_item(self):
        with schema_context(self.tenant.schema_name):
            other = CartItem.objects.create(
                user=self.staff, product=self.shampoo, quantity=1, price=Decimal("150.50")
            )

        self.authenticate(self.customer)
        response = self.client.delete(
            reverse("cart-item-detail", args=[other.id])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class InvoiceApiTests(ProductSalesTestCase):
    def test_creating_an_invoice_from_the_cart_deducts_stock(self):
        """
        The items used to be written with bulk_create(), which skips
        InvoiceItem.save() - so an order was raised but the stock was never
        taken off the shelf.
        """
        with schema_context(self.tenant.schema_name):
            CartItem.objects.create(
                user=self.customer,
                product=self.shampoo,
                quantity=4,
                price=Decimal("150.50"),
            )

        self.authenticate(self.customer)
        response = self.client.post(
            reverse("invoice-list"),
            {"shipping_address": "12 High Street", "payment_method": "cod"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        with schema_context(self.tenant.schema_name):
            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 6)
            self.assertFalse(CartItem.objects.filter(user=self.customer).exists())

    def test_each_invoice_gets_its_own_number(self):
        """
        invoice_number is read-only on the serializer and was never populated,
        so every invoice saved an empty string and the second one violated the
        unique constraint.
        """
        self.authenticate(self.customer)
        numbers = []

        for _ in range(2):
            with schema_context(self.tenant.schema_name):
                CartItem.objects.create(
                    user=self.customer,
                    product=self.shampoo,
                    quantity=1,
                    price=Decimal("150.50"),
                )

            response = self.client.post(
                reverse("invoice-list"), {"payment_method": "cod"}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            numbers.append(response.data["data"]["invoice_number"])

        self.assertTrue(all(numbers))
        self.assertEqual(len(set(numbers)), 2)

    def test_checkout_is_refused_when_the_cart_exceeds_stock(self):
        with schema_context(self.tenant.schema_name):
            CartItem.objects.create(
                user=self.customer,
                product=self.shampoo,
                quantity=4,
                price=Decimal("150.50"),
            )
            self.shampoo.current_stock = 1
            self.shampoo.save(update_fields=["current_stock"])

        self.authenticate(self.customer)
        response = self.client.post(
            reverse("invoice-list"), {"payment_method": "cod"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        with schema_context(self.tenant.schema_name):
            self.assertFalse(Invoice.objects.filter(user=self.customer).exists())

    def test_an_empty_cart_cannot_be_checked_out(self):
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("invoice-list"), {"payment_method": "cod"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_customer_only_sees_their_own_invoices(self):
        with schema_context(self.tenant.schema_name):
            Invoice.objects.create(
                invoice_number=build_invoice_number(), user=self.staff
            )
            mine = Invoice.objects.create(
                invoice_number=build_invoice_number(), user=self.customer
            )

        self.authenticate(self.customer)
        response = self.client.get(reverse("invoice-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"]
        self.assertEqual([row["id"] for row in rows], [str(mine.id)])


class ProductCatalogueApiTests(ProductSalesTestCase):
    """
    Catalogue writes are staff/admin operations.

    Every one of these used to be open to any signed-in customer: the viewsets
    defined ``get_permission_classes``, which DRF never calls.
    """

    def test_a_customer_cannot_create_a_product_category(self):
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("product-category-list"),
            {"name": "Skin Care"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create_a_product_category(self):
        self.authenticate(self.staff)

        response = self.client.post(
            reverse("product-category-list"),
            {"name": "Skin Care"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_a_customer_cannot_delete_a_product_category(self):
        self.authenticate(self.customer)

        response = self.client.delete(
            reverse("product-category-detail", args=[self.category.id])
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_only_an_admin_can_delete_a_product(self):
        self.authenticate(self.staff)
        refused = self.client.delete(
            reverse("product-detail", args=[self.shampoo.id])
        )
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.admin)
        allowed = self.client.delete(
            reverse("product-detail", args=[self.shampoo.id])
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

    def test_a_customer_cannot_change_a_products_price(self):
        self.authenticate(self.customer)

        response = self.client.patch(
            reverse("product-detail", args=[self.shampoo.id]),
            {"selling_price": "0.01"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        with schema_context(self.tenant.schema_name):
            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.selling_price, Decimal("150.50"))

    def test_any_signed_in_user_can_browse_the_catalogue(self):
        self.authenticate(self.customer)

        self.assertEqual(
            self.client.get(reverse("product-list")).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.get(reverse("product-category-list")).status_code,
            status.HTTP_200_OK,
        )

    def test_anonymous_users_cannot_browse_the_catalogue(self):
        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProductModelTests(ProductSalesTestCase):
    def test_low_stock_flag_tracks_the_minimum(self):
        with schema_context(self.tenant.schema_name):
            self.assertFalse(self.shampoo.is_low_stock)

            self.shampoo.current_stock = 2
            self.assertTrue(self.shampoo.is_low_stock)

    def test_in_stock_flag(self):
        with schema_context(self.tenant.schema_name):
            self.assertTrue(self.shampoo.is_in_stock)

            self.shampoo.current_stock = 0
            self.assertFalse(self.shampoo.is_in_stock)
