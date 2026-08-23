from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from django_tenants.utils import schema_context

from rest_framework import status

from product_sales.models import Product, ProductCategory
from stock_management.models import StockPurchase, StockPurchaseItem
from utils.testing import TenantAPITestCase


class StockManagementTestCase(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with schema_context(self.tenant.schema_name):
            self.category = ProductCategory.objects.create(name="Hair Care")
            self.shampoo = Product.objects.create(
                name="Shampoo",
                product_category=self.category,
                current_stock=5,
                purchase_price=Decimal("90.00"),
                selling_price=Decimal("150.00"),
            )
            self.conditioner = Product.objects.create(
                name="Conditioner",
                product_category=self.category,
                current_stock=0,
                purchase_price=Decimal("80.00"),
                selling_price=Decimal("120.00"),
            )

    def purchase_payload(self, **overrides):
        payload = {
            "invoice_number": "SUP-001",
            "purchase_date": "2030-01-10",
            "payment_status": "unpaid",
            "supplier_details": {"name": "Acme Supplies"},
            "items": [
                {
                    "product": str(self.shampoo.id),
                    "quantity": 10,
                    "purchase_price": "90.00",
                }
            ],
        }
        payload.update(overrides)
        return payload


class StockPurchaseItemModelTests(StockManagementTestCase):
    def test_receiving_a_purchase_adds_to_stock(self):
        with schema_context(self.tenant.schema_name):
            purchase = StockPurchase.objects.create(purchase_date="2030-01-10")

            StockPurchaseItem.objects.create(
                stock_purchase=purchase,
                product=self.shampoo,
                quantity=10,
                purchase_price=Decimal("90.00"),
            )

            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 15)

    def test_the_purchase_price_is_copied_onto_the_product(self):
        with schema_context(self.tenant.schema_name):
            purchase = StockPurchase.objects.create(purchase_date="2030-01-10")

            StockPurchaseItem.objects.create(
                stock_purchase=purchase,
                product=self.shampoo,
                quantity=1,
                purchase_price=Decimal("95.50"),
            )

            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.purchase_price, Decimal("95.50"))

    def test_subtotal_and_purchase_total_are_derived(self):
        with schema_context(self.tenant.schema_name):
            purchase = StockPurchase.objects.create(purchase_date="2030-01-10")

            item = StockPurchaseItem.objects.create(
                stock_purchase=purchase,
                product=self.shampoo,
                quantity=3,
                purchase_price=Decimal("90.00"),
            )

            item.refresh_from_db()
            purchase.refresh_from_db()
            self.assertEqual(item.subtotal, Decimal("270.00"))
            self.assertEqual(purchase.total_amount, Decimal("270.00"))

    def test_changing_a_quantity_only_moves_the_difference(self):
        with schema_context(self.tenant.schema_name):
            purchase = StockPurchase.objects.create(purchase_date="2030-01-10")
            item = StockPurchaseItem.objects.create(
                stock_purchase=purchase,
                product=self.shampoo,
                quantity=10,
                purchase_price=Decimal("90.00"),
            )

            item.quantity = 4
            item.save()

            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 9)

    def test_removing_a_purchase_line_takes_the_units_back_out(self):
        with schema_context(self.tenant.schema_name):
            purchase = StockPurchase.objects.create(purchase_date="2030-01-10")
            item = StockPurchaseItem.objects.create(
                stock_purchase=purchase,
                product=self.shampoo,
                quantity=10,
                purchase_price=Decimal("90.00"),
            )

            item.delete()

            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 5)

    def test_a_reversal_that_would_drive_stock_negative_is_refused(self):
        """
        The received units have already been sold on, so undoing the purchase
        would push current_stock below zero. That used to surface as a raw
        database constraint error.
        """
        with schema_context(self.tenant.schema_name):
            purchase = StockPurchase.objects.create(purchase_date="2030-01-10")
            item = StockPurchaseItem.objects.create(
                stock_purchase=purchase,
                product=self.conditioner,
                quantity=10,
                purchase_price=Decimal("80.00"),
            )

            self.conditioner.refresh_from_db()
            self.conditioner.current_stock = 2
            self.conditioner.save(update_fields=["current_stock"])

            with self.assertRaises(ValidationError):
                item.delete()

            self.conditioner.refresh_from_db()
            self.assertEqual(self.conditioner.current_stock, 2)


class StockPurchaseApiTests(StockManagementTestCase):
    def test_staff_can_record_a_purchase_and_stock_goes_up(self):
        self.authenticate(self.staff)

        response = self.client.post(
            reverse("stock-purchases-list"), self.purchase_payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with schema_context(self.tenant.schema_name):
            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 15)
            self.assertEqual(StockPurchase.objects.count(), 1)

    def test_a_customer_cannot_record_a_purchase(self):
        self.authenticate(self.customer)

        response = self.client.post(
            reverse("stock-purchases-list"), self.purchase_payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        with schema_context(self.tenant.schema_name):
            self.assertEqual(StockPurchase.objects.count(), 0)

    def test_only_an_admin_can_delete_a_purchase(self):
        self.authenticate(self.staff)
        created = self.client.post(
            reverse("stock-purchases-list"), self.purchase_payload(), format="json"
        )
        purchase_id = created.data["data"]["id"]

        refused = self.client.delete(
            reverse("stock-purchases-detail", args=[purchase_id])
        )
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.admin)
        allowed = self.client.delete(
            reverse("stock-purchases-detail", args=[purchase_id])
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

    def test_a_purchase_with_no_items_is_rejected(self):
        self.authenticate(self.staff)

        response = self.client.post(
            reverse("stock-purchases-list"),
            self.purchase_payload(items=[]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_zero_quantity_line_is_rejected(self):
        self.authenticate(self.staff)

        response = self.client.post(
            reverse("stock-purchases-list"),
            self.purchase_payload(
                items=[
                    {
                        "product": str(self.shampoo.id),
                        "quantity": 0,
                        "purchase_price": "90.00",
                    }
                ]
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_updating_a_line_by_id_edits_it_instead_of_replacing_it(self):
        """
        The item id was read-only on the serializer, so it never reached
        validated_data and every update deleted and recreated the whole item
        set rather than editing the line the caller named.
        """
        self.authenticate(self.staff)
        created = self.client.post(
            reverse("stock-purchases-list"), self.purchase_payload(), format="json"
        )
        purchase_id = created.data["data"]["id"]
        item_id = created.data["data"]["items"][0]["id"]

        response = self.client.patch(
            reverse("stock-purchases-detail", args=[purchase_id]),
            {
                "items": [
                    {
                        "id": item_id,
                        "product": str(self.shampoo.id),
                        "quantity": 4,
                        "purchase_price": "90.00",
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = response.data["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], item_id)
        self.assertEqual(items[0]["quantity"], 4)

        with schema_context(self.tenant.schema_name):
            self.shampoo.refresh_from_db()
            self.assertEqual(self.shampoo.current_stock, 9)

    def test_an_item_id_from_another_purchase_is_rejected(self):
        self.authenticate(self.staff)
        first = self.client.post(
            reverse("stock-purchases-list"), self.purchase_payload(), format="json"
        )
        second = self.client.post(
            reverse("stock-purchases-list"),
            self.purchase_payload(invoice_number="SUP-002"),
            format="json",
        )
        foreign_item_id = second.data["data"]["items"][0]["id"]

        response = self.client.patch(
            reverse("stock-purchases-detail", args=[first.data["data"]["id"]]),
            {
                "items": [
                    {
                        "id": foreign_item_id,
                        "product": str(self.shampoo.id),
                        "quantity": 1,
                        "purchase_price": "90.00",
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_dropping_a_line_from_the_payload_removes_it(self):
        self.authenticate(self.staff)
        created = self.client.post(
            reverse("stock-purchases-list"),
            self.purchase_payload(
                items=[
                    {
                        "product": str(self.shampoo.id),
                        "quantity": 10,
                        "purchase_price": "90.00",
                    },
                    {
                        "product": str(self.conditioner.id),
                        "quantity": 6,
                        "purchase_price": "80.00",
                    },
                ]
            ),
            format="json",
        )
        purchase_id = created.data["data"]["id"]
        keep_id = [
            item["id"]
            for item in created.data["data"]["items"]
            if item["product_name"] == "Shampoo"
        ][0]

        response = self.client.patch(
            reverse("stock-purchases-detail", args=[purchase_id]),
            {
                "items": [
                    {
                        "id": keep_id,
                        "product": str(self.shampoo.id),
                        "quantity": 10,
                        "purchase_price": "90.00",
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["items"]), 1)
        with schema_context(self.tenant.schema_name):
            self.conditioner.refresh_from_db()
            self.assertEqual(self.conditioner.current_stock, 0)

    def test_any_signed_in_user_can_read_purchases(self):
        self.authenticate(self.customer)

        response = self.client.get(reverse("stock-purchases-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_anonymous_access_is_refused(self):
        response = self.client.get(reverse("stock-purchases-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
