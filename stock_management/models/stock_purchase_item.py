from django.db import models, transaction
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
            super().save(*args, **kwargs)
 
            product = self.product
            if is_new:
                product.current_stock = models.F("current_stock") + self.quantity
            else:
                diff = self.quantity - old_quantity
                product.current_stock = models.F("current_stock") + diff
 
            # keep the product's cost price up to date with the latest purchase
            product.purchase_price = self.purchase_price
            product.save(update_fields=["current_stock", "purchase_price"])
 
        self.stock_purchase.recalc_total()
 
    def delete(self, *args, **kwargs):
        with transaction.atomic():
            product = self.product
            product.current_stock = models.F("current_stock") - self.quantity
            product.save(update_fields=["current_stock"])
            super().delete(*args, **kwargs)
        self.stock_purchase.recalc_total()