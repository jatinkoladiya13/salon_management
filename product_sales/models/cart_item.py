from django.db import models
import uuid


class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "account.User",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    product = models.ForeignKey(
        "product_sales.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        db_table = "cart_item"
        verbose_name = "Cart Item"
        verbose_name_plural = "Cart Items"
        ordering = ["product"]
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.quantity}"
    
    @property
    def subtotal(self):
        return self.price * self.quantity