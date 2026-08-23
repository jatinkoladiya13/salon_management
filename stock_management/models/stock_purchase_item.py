from django.core.exceptions import ValidationError
from django.db import models, transaction

from product_sales.models import Product

import uuid

class StockPurchaseItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stock_purchase = models.ForeignKey(
        "stock_management.StockPurchase",
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "product_sales.Product",
        on_delete=models.CASCADE,
        related_name="purchase_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        db_table = "stock_purchase_item"
        verbose_name = "Stock Purchase Item"
        verbose_name_plural = "Stock Purchase Items"
        ordering = ["stock_purchase"]
        indexes = [
            models.Index(fields=["stock_purchase"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.quantity}"
    
    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.purchase_price
        is_new = self._state.adding
        old_quantity = None if is_new else StockPurchaseItem.objects.get(pk=self.pk).quantity

        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.product_id)

            delta = self.quantity if is_new else self.quantity - old_quantity

            super().save(*args, **kwargs)

            product.current_stock = models.F("current_stock") + delta
            # keep the product's cost price up to date with the latest purchase
            product.purchase_price = self.purchase_price
            product.save(update_fields=["current_stock", "purchase_price"])
            product.refresh_from_db(fields=["current_stock"])
            self.product = product

        self.stock_purchase.recalc_total()

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.product_id)

            if self.quantity > product.current_stock:
                # The purchased units have already been sold on, so reversing
                # the purchase would take current_stock below zero and trip the
                # PositiveIntegerField constraint with an opaque database error.
                raise ValidationError(
                    f"Cannot remove this purchase line: only "
                    f"{product.current_stock} of {product.name} remain in stock "
                    f"but the line added {self.quantity}."
                )

            product.current_stock = models.F("current_stock") - self.quantity
            product.save(update_fields=["current_stock"])
            super().delete(*args, **kwargs)
        self.stock_purchase.recalc_total()